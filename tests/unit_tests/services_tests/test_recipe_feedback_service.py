from datetime import date, datetime, time

import pytest

from mealie.core.exceptions import NoEntryFound
from mealie.schema.household.household import HouseholdRecipeUpdate
from mealie.schema.household.recipe_feedback import FeedbackVerdict, RecipeFeedbackCreate
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.user.user import PrivateUser, UserRatingCreate
from mealie.services.claude_context import recipe_feedback_service
from mealie.services.claude_context.recipe_feedback_service import (
    VERDICT_RATING,
    VERDICT_SUBJECT,
    RecipeFeedbackService,
)
from mealie.services.household_services.household_service import HouseholdService
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

DAY_1 = date(2026, 10, 20)
DAY_2 = date(2026, 10, 24)


def _recipe(user: TestUser) -> Recipe:
    return user.repos.recipes.create(
        Recipe(name=random_string(10), user_id=user.user_id, group_id=user.group_id, household_id=user.household_id)
    )


def _service(user: TestUser) -> RecipeFeedbackService:
    private_user = user.repos.users.get_one(user.user_id)
    assert isinstance(private_user, PrivateUser)
    return RecipeFeedbackService(user.repos, private_user)


def _noon(day: date) -> datetime:
    """`made_on` at 12:00 local time, as the service stores last made and the timeline timestamp."""
    return datetime.combine(day, time(12)).astimezone()


def _last_made(user: TestUser, recipe: Recipe) -> datetime | None:
    user.repos.session.expire_all()
    household_recipe = user.repos.household_recipes.get_by_recipe(recipe.id)
    return household_recipe.last_made if household_recipe else None


def _rating(user: TestUser, recipe: Recipe):
    user.repos.session.expire_all()
    return user.repos.user_ratings.get_by_user_and_recipe(user.user_id, recipe.id)


def test_record_creates_row_rating_timeline_and_last_made(unique_user: TestUser):
    recipe = _recipe(unique_user)

    out = _service(unique_user).record(
        RecipeFeedbackCreate(
            recipe_id=recipe.id, verdict=FeedbackVerdict.loved, effort=2, note="Crispy edges", for_whom="Sam"
        ),
        today=DAY_2,
    )

    assert out.made_on == DAY_2
    assert out.verdict == FeedbackVerdict.loved
    assert (out.effort, out.note, out.for_whom) == (2, "Crispy edges", "Sam")
    assert str(out.user_id) == str(unique_user.user_id)
    assert str(out.household_id) == str(unique_user.household_id)
    assert out.recipe.slug == recipe.slug
    assert unique_user.repos.recipe_feedback.get_one(out.id) is not None

    assert _last_made(unique_user, recipe) == _noon(DAY_2)

    rating = _rating(unique_user, recipe)
    assert rating is not None
    assert rating.rating == 5
    assert rating.is_favorite is False

    assert out.timeline_event_id is not None
    event = unique_user.repos.recipe_timeline_events.get_one(out.timeline_event_id)
    assert event is not None
    assert event.recipe_id == recipe.id
    assert str(event.user_id) == str(unique_user.user_id)
    assert event.subject == VERDICT_SUBJECT[FeedbackVerdict.loved]
    assert event.event_type == "comment"
    assert event.message == "Crispy edges"
    assert event.timestamp == _noon(DAY_2)


def test_last_made_only_moves_forward(unique_user: TestUser):
    recipe = _recipe(unique_user)
    service = _service(unique_user)

    service.record(RecipeFeedbackCreate(recipe_id=recipe.id, verdict=FeedbackVerdict.ok, made_on=DAY_2))
    assert _last_made(unique_user, recipe) == _noon(DAY_2)

    # an older verdict is recorded, but last made stays where it was
    old = service.record(RecipeFeedbackCreate(recipe_id=recipe.id, verdict=FeedbackVerdict.loved, made_on=DAY_1))
    assert old.made_on == DAY_1
    assert _last_made(unique_user, recipe) == _noon(DAY_2)

    # a last made set elsewhere (e.g. "I made this" later in the day) is not pulled back to noon
    evening = datetime.combine(date(2026, 10, 25), time(20)).astimezone()
    HouseholdService(unique_user.group_id, unique_user.household_id, unique_user.repos).set_household_recipe(
        recipe.slug, HouseholdRecipeUpdate(last_made=evening)
    )
    service.record(RecipeFeedbackCreate(recipe_id=recipe.id, verdict=FeedbackVerdict.ok, made_on=date(2026, 10, 25)))
    assert _last_made(unique_user, recipe) == evening


@pytest.mark.parametrize(
    "verdict, rating", [(FeedbackVerdict.loved, 5), (FeedbackVerdict.ok, 3), (FeedbackVerdict.never_again, 1)]
)
def test_rating_mapping(unique_user: TestUser, verdict: FeedbackVerdict, rating: int):
    recipe = _recipe(unique_user)

    _service(unique_user).record(RecipeFeedbackCreate(recipe_id=recipe.id, verdict=verdict), today=DAY_2)

    assert VERDICT_RATING[verdict] == rating
    stored = _rating(unique_user, recipe)
    assert stored is not None
    assert stored.rating == rating


def test_rating_keeps_favourite(unique_user: TestUser):
    recipe = _recipe(unique_user)
    unique_user.repos.user_ratings.create(
        UserRatingCreate(user_id=unique_user.user_id, recipe_id=recipe.id, rating=5, is_favorite=True)
    )

    _service(unique_user).record(
        RecipeFeedbackCreate(recipe_id=recipe.id, verdict=FeedbackVerdict.never_again), today=DAY_2
    )

    stored = _rating(unique_user, recipe)
    assert stored is not None
    assert stored.rating == 1
    assert stored.is_favorite is True
    assert len(unique_user.repos.user_ratings.get_by_recipe(recipe.id)) == 1


def test_delete_removes_timeline_event_only(unique_user: TestUser):
    recipe = _recipe(unique_user)
    service = _service(unique_user)
    out = service.record(RecipeFeedbackCreate(recipe_id=recipe.id, verdict=FeedbackVerdict.loved), today=DAY_2)
    assert out.timeline_event_id is not None

    deleted = service.delete(out.id)

    assert deleted.id == out.id
    unique_user.repos.session.expire_all()
    assert unique_user.repos.recipe_feedback.get_one(out.id) is None
    assert unique_user.repos.recipe_timeline_events.get_one(out.timeline_event_id) is None
    # last made and rating are left as they are
    assert _last_made(unique_user, recipe) == _noon(DAY_2)
    rating = _rating(unique_user, recipe)
    assert rating is not None
    assert rating.rating == 5

    # a row whose timeline event was already removed by hand still deletes
    second = service.record(RecipeFeedbackCreate(recipe_id=recipe.id, verdict=FeedbackVerdict.ok), today=DAY_2)
    assert second.timeline_event_id is not None
    unique_user.repos.recipe_timeline_events.delete(second.timeline_event_id)
    service.delete(second.id)
    assert unique_user.repos.recipe_feedback.get_one(second.id) is None

    with pytest.raises(NoEntryFound):
        service.delete(out.id)


def test_record_rejects_foreign_recipe(unique_user: TestUser, g2_user: TestUser, h2_user: TestUser):
    foreign = _recipe(g2_user)
    service = _service(unique_user)

    with pytest.raises(NoEntryFound):
        service.record(RecipeFeedbackCreate(recipe_id=foreign.id, verdict=FeedbackVerdict.loved), today=DAY_2)

    # nothing was written anywhere
    g2_user.repos.session.expire_all()
    assert unique_user.repos.user_ratings.get_by_user_and_recipe(unique_user.user_id, foreign.id) is None
    assert g2_user.repos.household_recipes.get_by_recipe(foreign.id) is None
    timeline = g2_user.repos.recipe_timeline_events.multi_query({"recipe_id": foreign.id})
    assert timeline == []
    assert g2_user.repos.recipe_feedback.summaries([foreign.id]) == {}
    assert unique_user.repos.recipe_feedback.summaries([foreign.id]) == {}

    # feedback from another household cannot be deleted either
    own = _service(h2_user).record(
        RecipeFeedbackCreate(recipe_id=_recipe(h2_user).id, verdict=FeedbackVerdict.ok), today=DAY_2
    )
    with pytest.raises(NoEntryFound):
        service.delete(own.id)
    assert h2_user.repos.recipe_feedback.get_one(own.id) is not None


def test_summary_ignores_deleted_recipe(unique_user: TestUser):
    kept = _recipe(unique_user)
    gone = _recipe(unique_user)
    service = _service(unique_user)
    service.record(RecipeFeedbackCreate(recipe_id=kept.id, verdict=FeedbackVerdict.loved), today=DAY_2)
    service.record(RecipeFeedbackCreate(recipe_id=gone.id, verdict=FeedbackVerdict.never_again), today=DAY_2)

    unique_user.repos.recipes.delete(gone.slug)
    unique_user.repos.session.expire_all()

    summaries = service.summaries([kept.id, gone.id])
    assert set(summaries) == {kept.id}
    assert summaries[kept.id].last_verdict == FeedbackVerdict.loved
    assert gone.id not in {row.recipe.id for row in service.list(None, 1, -1).items}


def test_made_on_defaults_to_today(unique_user: TestUser, monkeypatch: pytest.MonkeyPatch):
    recipe = _recipe(unique_user)
    service = _service(unique_user)

    explicit = service.record(RecipeFeedbackCreate(recipe_id=recipe.id, verdict=FeedbackVerdict.ok), today=DAY_1)
    assert explicit.made_on == DAY_1

    # freeze the service's clock just before local midnight, so the test cannot straddle a day boundary
    frozen = datetime.combine(date(2026, 3, 7), time(23, 59, 59)).astimezone()

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen if tz is None else frozen.astimezone(tz)

    monkeypatch.setattr(recipe_feedback_service, "datetime", FrozenDatetime)
    implicit = service.record(RecipeFeedbackCreate(recipe_id=recipe.id, verdict=FeedbackVerdict.ok))
    assert implicit.made_on == date(2026, 3, 7)


def test_list_pages_newest_first(unique_user: TestUser):
    recipe = _recipe(unique_user)
    other = _recipe(unique_user)
    service = _service(unique_user)
    rows = [
        service.record(RecipeFeedbackCreate(recipe_id=recipe.id, verdict=FeedbackVerdict.ok, made_on=day))
        for day in (DAY_1, DAY_2, date(2026, 10, 22))
    ]
    service.record(RecipeFeedbackCreate(recipe_id=other.id, verdict=FeedbackVerdict.loved, made_on=DAY_2))

    first = service.list(recipe.id, page=1, per_page=2)
    assert (first.total, first.total_pages, first.page, first.per_page) == (3, 2, 1, 2)
    assert [row.id for row in first.items] == [rows[1].id, rows[2].id]
    second = service.list(recipe.id, page=2, per_page=2)
    assert [row.id for row in second.items] == [rows[0].id]
    everything = service.list(recipe.id, page=1, per_page=-1)
    assert (everything.total, everything.total_pages, len(everything.items)) == (3, 1, 3)
