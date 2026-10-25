from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from mealie.core.config import get_app_settings
from mealie.db.models.household.household import Household
from mealie.db.models.users.users import User
from mealie.schema.household.household_profile import (
    Diet,
    HouseholdProfileOut,
    MealPreferencesUpdate,
    MemberProfileCreate,
    MemberProfileUpdate,
)
from mealie.services.query_filter.builder import NonFilterableValueError, QueryFilterBuilder
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

# unique_user is shared across this module: every test tags its names and only looks at its own rows.


def test_member_profile_round_trip_with_list_defaults(unique_user: TestUser):
    repo = unique_user.repos.member_profiles
    name = f"Sam {random_string(8)}"

    created = repo.create(MemberProfileCreate(name=name))

    fetched = repo.get_one(created.id)
    assert fetched is not None
    assert fetched.name == name
    assert fetched.user_id is None
    assert fetched.is_child is False
    assert fetched.diet == Diet.none
    assert fetched.allergies == []
    assert fetched.exclusions == []
    assert fetched.dislikes == []
    assert fetched.likes == []
    assert fetched.notes is None
    assert fetched.position == 0
    assert str(fetched.group_id) == str(unique_user.group_id)
    assert str(fetched.household_id) == str(unique_user.household_id)
    assert fetched.created_at is not None


def test_member_profile_round_trip_with_lists(unique_user: TestUser):
    repo = unique_user.repos.member_profiles
    created = repo.create(
        MemberProfileCreate(
            name=f"Alex {random_string(8)}",
            is_child=True,
            diet=Diet.vegetarian,
            allergies=["peanuts", "Crème fraîche"],
            exclusions=["pork"],
            dislikes=["mushrooms"],
            likes=["pasta"],
            notes="Picky at dinner",
            position=3,
        )
    )

    fetched = repo.get_one(created.id)
    assert fetched is not None
    assert fetched.is_child is True
    assert fetched.diet == Diet.vegetarian
    assert fetched.allergies == ["peanuts", "Crème fraîche"]
    assert fetched.exclusions == ["pork"]
    assert fetched.dislikes == ["mushrooms"]
    assert fetched.likes == ["pasta"]
    assert fetched.notes == "Picky at dinner"
    assert fetched.position == 3


def test_meal_preferences_round_trip_with_list_defaults(h2_user: TestUser):
    repo = h2_user.repos.meal_preferences
    assert repo.get_for_household() is None

    created = repo.create(MealPreferencesUpdate(default_servings=4))

    fetched = repo.get_for_household()
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.default_servings == 4
    assert fetched.quick_weekdays == []
    assert fetched.favourite_cuisines == []
    assert fetched.weeknight_max_minutes is None
    assert fetched.weekend_max_minutes is None
    assert fetched.notes is None
    assert str(fetched.household_id) == str(h2_user.household_id)

    # one row per household
    with pytest.raises(IntegrityError):
        repo.create(MealPreferencesUpdate())
    repo.session.rollback()


def test_ordered_by_position_then_name_then_id(unique_user: TestUser):
    tag = random_string(8)
    repo = unique_user.repos.member_profiles
    repo.create(MemberProfileCreate(name=f"{tag} zoe", position=1))
    repo.create(MemberProfileCreate(name=f"{tag} Bob", position=2))
    repo.create(MemberProfileCreate(name=f"{tag} amy", position=2))
    repo.create(MemberProfileCreate(name=f"{tag} Émile", position=0))

    names = [row.name for row in repo.ordered() if row.name.startswith(tag)]
    assert names == [f"{tag} Émile", f"{tag} zoe", f"{tag} amy", f"{tag} Bob"]


def test_ordered_ties_break_on_id_desc(unique_user: TestUser):
    tag = random_string(8)
    repo = unique_user.repos.member_profiles
    stamp = datetime(2099, 2, 1, 12, 0, tzinfo=UTC)
    rows = repo.create_many(
        [{**MemberProfileCreate(name=f"{tag} same").model_dump(), "created_at": stamp} for _ in range(3)]
    )
    by_id_desc = sorted(rows, key=lambda row: str(row.id).replace("-", ""), reverse=True)

    assert [row.id for row in repo.ordered() if row.name.startswith(tag)] == [row.id for row in by_id_desc]


def test_by_user_and_by_name_casefold(unique_user: TestUser):
    repo = unique_user.repos.member_profiles
    tag = random_string(8)
    linked = repo.create(MemberProfileCreate(name=f"Crème {tag}", user_id=unique_user.user_id))

    found = repo.by_user(unique_user.user_id)
    assert found is not None
    assert found.id == linked.id

    by_name = repo.by_name_casefold(f"  CRÈME {tag.upper()} ")
    assert by_name is not None
    assert by_name.id == linked.id
    assert repo.by_name_casefold(f"nobody {tag}") is None

    # at most one profile per user per household
    with pytest.raises(IntegrityError):
        repo.create(MemberProfileCreate(name=f"Other {tag}", user_id=unique_user.user_id))
    repo.session.rollback()

    # unlinked profiles never collide with each other
    repo.create(MemberProfileCreate(name=f"Kid one {tag}"))
    repo.create(MemberProfileCreate(name=f"Kid two {tag}"))


def test_profiles_are_scoped_to_household_and_group(unique_user: TestUser, h2_user: TestUser, g2_user: TestUser):
    tag = random_string(8)
    created = unique_user.repos.member_profiles.create(MemberProfileCreate(name=f"Secret {tag}"))
    prefs = unique_user.repos.meal_preferences.get_for_household() or unique_user.repos.meal_preferences.create(
        MealPreferencesUpdate(notes=tag)
    )

    for other in (h2_user, g2_user):
        assert other.repos.member_profiles.get_one(created.id) is None
        assert created.id not in {row.id for row in other.repos.member_profiles.ordered()}
        assert other.repos.member_profiles.by_name_casefold(f"Secret {tag}") is None
        other_prefs = other.repos.meal_preferences.get_for_household()
        assert other_prefs is None or other_prefs.id != prefs.id

    # a scoped repository always writes its own scope, whatever the payload says
    forced = unique_user.repos.member_profiles.create(
        {
            **MemberProfileCreate(name=f"Forced {tag}").model_dump(),
            "group_id": g2_user.group_id,
            "household_id": h2_user.household_id,
        }
    )
    assert str(forced.household_id) == str(unique_user.household_id)
    assert str(forced.group_id) == str(unique_user.group_id)
    many = unique_user.repos.member_profiles.create_many(
        [{**MemberProfileCreate(name=f"Many {tag}").model_dump(), "household_id": h2_user.household_id}]
    )
    assert {str(row.household_id) for row in many} == {str(unique_user.household_id)}


def test_deleting_the_linked_user_keeps_the_profile(unique_user: TestUser):
    repos = unique_user.repos
    group = repos.groups.get_one(unique_user.group_id)
    household = repos.households.get_one(unique_user.household_id)
    assert group is not None and household is not None
    extra = repos.users.create(
        {
            "username": random_string(),
            "email": f"{random_string()}@example.com",
            "group": group.name,
            "household": household.name,
            "full_name": "Leaving",
            "password": random_string(),
            "admin": False,
        }
    )
    profile = repos.member_profiles.create(MemberProfileCreate(name=f"Leaving {random_string(8)}", user_id=extra.id))

    repos.users.delete(extra.id)
    repos.session.expire_all()

    kept = repos.member_profiles.get_one(profile.id)
    assert kept is not None
    # `ondelete="SET NULL"` is enforced by PostgreSQL; Mealie does not enable SQLite foreign keys, so there the
    # stale id stays (harmless: user ids are UUIDs and never reused).
    if get_app_settings().DB_ENGINE == "postgres":
        assert kept.user_id is None


def test_household_profile_out_shape():
    out = HouseholdProfileOut(members=[], preferences=None)
    assert out.model_dump() == {"members": [], "preferences": None}


# --- write-schema normalisation ---


def test_lists_are_trimmed_deduplicated_and_emptied():
    data = MemberProfileCreate(
        name="  Sam  ",
        allergies=["  Peanuts ", "peanuts", "", "   ", "PEANUTS", "Crème", "crème", "Sesame"],
    )
    assert data.name == "Sam"
    assert data.allergies == ["Peanuts", "Crème", "Sesame"]


def test_list_item_longer_than_60_is_rejected():
    MemberProfileCreate(name="Sam", likes=["x" * 60])
    with pytest.raises(ValidationError):
        MemberProfileCreate(name="Sam", likes=["x" * 61])


def test_list_longer_than_30_is_rejected():
    MemberProfileCreate(name="Sam", dislikes=[f"item {i}" for i in range(30)])
    with pytest.raises(ValidationError):
        MemberProfileCreate(name="Sam", dislikes=[f"item {i}" for i in range(31)])
    # duplicates do not count towards the limit
    assert len(MemberProfileCreate(name="Sam", dislikes=[f"item {i % 30}" for i in range(40)]).dislikes) == 30


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_name_is_rejected(name: str):
    with pytest.raises(ValidationError):
        MemberProfileCreate(name=name)


def test_notes_longer_than_500_are_rejected():
    MemberProfileCreate(name="Sam", notes="x" * 500)
    with pytest.raises(ValidationError):
        MemberProfileCreate(name="Sam", notes="x" * 501)
    with pytest.raises(ValidationError):
        MealPreferencesUpdate(notes="x" * 501)


def test_diet_values_are_exact():
    assert [d.value for d in Diet] == ["none", "vegetarian", "vegan", "pescatarian", "halal", "kosher", "other"]
    with pytest.raises(ValidationError):
        MemberProfileCreate(name="Sam", diet="carnivore")


def test_member_update_is_partial():
    update = MemberProfileUpdate(likes=[" Pasta ", "pasta"])
    assert update.model_dump(exclude_unset=True) == {"likes": ["Pasta"]}
    assert MemberProfileUpdate().model_dump(exclude_unset=True) == {}
    assert MemberProfileUpdate(notes=None).model_dump(exclude_unset=True) == {"notes": None}


@pytest.mark.parametrize(
    "field", ["name", "is_child", "diet", "allergies", "exclusions", "dislikes", "likes", "position"]
)
def test_member_update_refuses_null_for_required_columns(field: str):
    with pytest.raises(ValidationError):
        MemberProfileUpdate(**{field: None})


def test_member_update_validates_like_create():
    with pytest.raises(ValidationError):
        MemberProfileUpdate(name="  ")
    with pytest.raises(ValidationError):
        MemberProfileUpdate(allergies=["x" * 61])


@pytest.mark.parametrize(
    "values",
    [
        {"default_servings": 0},
        {"default_servings": 21},
        {"weeknight_max_minutes": 4},
        {"weekend_max_minutes": 481},
        {"quick_weekdays": [7]},
        {"quick_weekdays": [-1]},
        {"quick_weekdays": None},
        {"favourite_cuisines": None},
        {"favourite_cuisines": ["x" * 61]},
    ],
)
def test_preferences_ranges_are_enforced(values: dict):
    with pytest.raises(ValidationError):
        MealPreferencesUpdate(**values)


def test_preferences_normalise():
    data = MealPreferencesUpdate(
        default_servings=20,
        quick_weekdays=[4, 0, 4, 6],
        weeknight_max_minutes=5,
        weekend_max_minutes=480,
        favourite_cuisines=[" Thai", "thai", "Italian", ""],
    )
    assert data.quick_weekdays == [0, 4, 6]
    assert data.favourite_cuisines == ["Thai", "Italian"]
    assert MealPreferencesUpdate(default_servings=None).model_dump(exclude_unset=True) == {"default_servings": None}


# --- query filters must never reach profiles or preferences ---


@pytest.mark.parametrize(
    "attr_string",
    [
        "member_profiles.name",
        "member_profiles.created_at",
        "member_profiles.household_id",
        "meal_preferences.notes",
        "meal_preferences.created_at",
    ],
)
def test_household_query_filters_cannot_reach_profiles(attr_string: str):
    with pytest.raises(NonFilterableValueError):
        QueryFilterBuilder.get_model_and_model_attr_from_attr_string(attr_string, Household)


@pytest.mark.parametrize("attr_string", ["household.member_profiles.name", "household.meal_preferences.notes"])
def test_member_query_filters_cannot_reach_profiles(attr_string: str):
    with pytest.raises(NonFilterableValueError):
        QueryFilterBuilder.get_model_and_model_attr_from_attr_string(attr_string, User)


def test_user_has_no_back_reference_to_profiles():
    assert not any("profile" in key for key in User.__mapper__.relationships.keys())
