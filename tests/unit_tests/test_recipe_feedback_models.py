from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mealie.schema.household.recipe_feedback import FeedbackVerdict, RecipeFeedbackCreate
from mealie.schema.recipe.recipe import Recipe
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def _recipe(user: TestUser) -> Recipe:
    return user.repos.recipes.create(
        Recipe(name=random_string(10), user_id=user.user_id, group_id=user.group_id, household_id=user.household_id)
    )


def _row(recipe: Recipe, verdict: FeedbackVerdict, made_on: date, **extra) -> dict:
    """A repository payload: the service decides `made_on`, so the repo always receives a date."""
    return RecipeFeedbackCreate(recipe_id=recipe.id, verdict=verdict, made_on=made_on, **extra).model_dump()


def test_recipe_feedback_round_trip_with_defaults(unique_user: TestUser):
    recipe = _recipe(unique_user)
    repo = unique_user.repos.recipe_feedback

    created = repo.create({**_row(recipe, FeedbackVerdict.loved, date(2026, 10, 24)), "user_id": unique_user.user_id})

    fetched = repo.get_one(created.id)
    assert fetched is not None
    assert fetched.verdict == FeedbackVerdict.loved
    assert fetched.made_on == date(2026, 10, 24)
    assert fetched.effort is None
    assert fetched.note is None
    assert fetched.for_whom is None
    assert fetched.timeline_event_id is None
    assert str(fetched.group_id) == str(unique_user.group_id)
    assert str(fetched.household_id) == str(unique_user.household_id)
    assert str(fetched.user_id) == str(unique_user.user_id)
    assert fetched.user_name == unique_user.full_name
    assert fetched.recipe.id == recipe.id
    assert fetched.recipe.slug == recipe.slug
    assert fetched.recipe.name == recipe.name
    assert fetched.created_at is not None


def test_for_recipe_orders_by_made_on_then_created_at(unique_user: TestUser):
    recipe = _recipe(unique_user)
    other = _recipe(unique_user)
    repo = unique_user.repos.recipe_feedback

    # unique_user is shared across this module: dates far ahead keep `latest` about these rows only
    older = repo.create(_row(recipe, FeedbackVerdict.ok, date(2099, 1, 1)))
    newest_first_recorded = repo.create(_row(recipe, FeedbackVerdict.loved, date(2099, 1, 20)))
    newest_last_recorded = repo.create(_row(recipe, FeedbackVerdict.never_again, date(2099, 1, 20)))
    repo.create(_row(other, FeedbackVerdict.loved, date(2099, 1, 22)))

    rows = repo.for_recipe(recipe.id)
    assert [row.id for row in rows] == [newest_last_recorded.id, newest_first_recorded.id, older.id]
    assert [row.id for row in repo.for_recipe(recipe.id, limit=1)] == [newest_last_recorded.id]

    latest = repo.latest(2)
    assert [row.id for row in latest][1] == newest_last_recorded.id
    assert latest[0].recipe.id == other.id


def test_summaries_count_verdicts_and_keep_the_last_one(unique_user: TestUser):
    first = _recipe(unique_user)
    second = _recipe(unique_user)
    untouched = _recipe(unique_user)
    repo = unique_user.repos.recipe_feedback

    repo.create(_row(first, FeedbackVerdict.loved, date(2026, 10, 1)))
    repo.create(_row(first, FeedbackVerdict.loved, date(2026, 10, 5)))
    repo.create(_row(first, FeedbackVerdict.ok, date(2026, 10, 10)))
    repo.create(_row(first, FeedbackVerdict.loved, date(2026, 9, 1)))  # recorded last, but made earliest
    repo.create(_row(second, FeedbackVerdict.never_again, date(2026, 10, 3)))

    summaries = repo.summaries([first.id, second.id, untouched.id])

    assert set(summaries) == {first.id, second.id}
    one = summaries[first.id]
    assert (one.loved, one.ok, one.never_again, one.total) == (3, 1, 0, 4)
    assert one.last_verdict == FeedbackVerdict.ok
    assert one.last_made_on == date(2026, 10, 10)
    two = summaries[second.id]
    assert (two.loved, two.ok, two.never_again, two.total) == (0, 0, 1, 1)
    assert two.last_verdict == FeedbackVerdict.never_again
    assert two.last_made_on == date(2026, 10, 3)
    assert repo.summaries([]) == {}


def test_recipe_feedback_is_scoped_to_household(unique_user: TestUser, h2_user: TestUser):
    recipe = _recipe(unique_user)
    created = unique_user.repos.recipe_feedback.create(_row(recipe, FeedbackVerdict.loved, date(2026, 10, 24)))
    other = h2_user.repos.recipe_feedback

    assert other.get_one(created.id) is None
    assert other.for_recipe(recipe.id) == []
    assert created.id not in {row.id for row in other.latest(100)}
    assert other.summaries([recipe.id]) == {}

    # a scoped repository always writes its own scope, whatever the payload says
    forced = unique_user.repos.recipe_feedback.create(
        {
            **_row(recipe, FeedbackVerdict.ok, date(2026, 10, 24)),
            "group_id": h2_user.group_id,
            "household_id": h2_user.household_id,
        }
    )
    assert str(forced.household_id) == str(unique_user.household_id)
    many = unique_user.repos.recipe_feedback.create_many(
        [{**_row(recipe, FeedbackVerdict.ok, date(2026, 10, 24)), "household_id": h2_user.household_id}]
    )
    assert {str(row.household_id) for row in many} == {str(unique_user.household_id)}


@pytest.mark.parametrize("effort", [0, 4, -1])
def test_effort_outside_one_to_three_is_rejected(effort: int):
    with pytest.raises(ValidationError):
        RecipeFeedbackCreate(recipe_id=uuid4(), verdict="loved", effort=effort)

    for valid in (1, 2, 3, None):
        assert RecipeFeedbackCreate(recipe_id=uuid4(), verdict="loved", effort=valid).effort == valid


def test_deleting_recipe_deletes_its_feedback(unique_user: TestUser):
    recipe = _recipe(unique_user)
    created = unique_user.repos.recipe_feedback.create(_row(recipe, FeedbackVerdict.loved, date(2026, 10, 24)))

    unique_user.repos.recipes.delete(recipe.slug)

    unique_user.repos.session.expire_all()
    assert unique_user.repos.recipe_feedback.get_one(created.id) is None
    assert unique_user.repos.recipe_feedback.summaries([recipe.id]) == {}
