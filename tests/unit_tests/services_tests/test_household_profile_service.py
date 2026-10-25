from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from mealie.core.config import get_app_settings
from mealie.core.exceptions import NoEntryFound
from mealie.db.models.household.household_profile import HouseholdMemberProfile
from mealie.repos.all_repositories import get_repositories
from mealie.schema.household.household_profile import (
    Diet,
    MealPreferencesUpdate,
    MemberProfileCreate,
    MemberProfileUpdate,
)
from mealie.schema.user.user import PrivateUser
from mealie.services.claude_context.household_profile_service import HouseholdProfileService, ProfileConflict
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

# Most tests use `unique_user_fn_scoped`: a fresh group and household per test, so the household starts empty.


def _service(user: TestUser) -> HouseholdProfileService:
    private_user = user.repos.users.get_one(user.user_id)
    assert isinstance(private_user, PrivateUser)
    return HouseholdProfileService(user.repos, private_user)


def _extra_user(user: TestUser) -> UUID:
    """Another Mealie user in `user`'s household."""
    repos = user.repos
    group = repos.groups.get_one(user.group_id)
    household = repos.households.get_one(user.household_id)
    assert group is not None and household is not None
    extra = repos.users.create(
        {
            "username": random_string(),
            "email": f"{random_string()}@example.com",
            "group": group.name,
            "household": household.name,
            "full_name": random_string(),
            "password": random_string(),
            "admin": False,
        }
    )
    return extra.id


# ------------------------------------------------------------------ reads


def test_get_empty_household(unique_user_fn_scoped: TestUser):
    out = _service(unique_user_fn_scoped).get()
    assert out.members == []
    assert out.preferences is None


def test_get_returns_ordered_members_and_preferences(unique_user_fn_scoped: TestUser):
    service = _service(unique_user_fn_scoped)
    service.create_member(MemberProfileCreate(name="Zoe", position=1))
    service.create_member(MemberProfileCreate(name="amy", position=1))
    service.create_member(MemberProfileCreate(name="Kid", position=0, is_child=True))
    service.update_preferences(MealPreferencesUpdate(default_servings=4))

    out = service.get()
    assert [m.name for m in out.members] == ["Kid", "amy", "Zoe"]
    assert out.preferences is not None
    assert out.preferences.default_servings == 4


def test_deleting_a_linked_user_unlinks_the_profile(unique_user_fn_scoped: TestUser):
    """On every database, not only where the FK's SET NULL is enforced (Mealie's SQLite runs without it)."""
    user = unique_user_fn_scoped
    extra = _extra_user(user)
    service = _service(user)
    created = service.create_member(MemberProfileCreate(name="Leaving", user_id=extra, allergies=["sesame"]))

    user.repos.users.delete(extra)
    user.repos.session.expire_all()

    members = service.get().members
    assert [(m.id, m.user_id, m.allergies) for m in members] == [(created.id, None, ["sesame"])]


@pytest.mark.skipif(get_app_settings().DB_ENGINE == "postgres", reason="PostgreSQL refuses a dangling user_id")
def test_get_survives_a_stale_user_id(unique_user_fn_scoped: TestUser):
    """A dangling `user_id` from before user deletion cleared it (SQLite, no FK enforcement); reads must not break."""
    user = unique_user_fn_scoped
    service = _service(user)
    created = service.create_member(MemberProfileCreate(name="Stale"))
    user.repos.session.execute(
        update(HouseholdMemberProfile).where(HouseholdMemberProfile.id == created.id).values(user_id=uuid4())
    )
    user.repos.session.commit()

    assert [m.id for m in service.get().members] == [created.id]
    # still editable without clearing the stale link (only a changed user_id is checked)
    assert service.update_member(created.id, MemberProfileUpdate(likes=["soup"])).likes == ["soup"]


# ------------------------------------------------------------------ normalisation


def test_normalise_list_reuses_the_schema_rules():
    assert HouseholdProfileService.normalise_list(["  Peanuts ", "peanuts", "", "Crème", "CRÈME"]) == [
        "Peanuts",
        "Crème",
    ]
    with pytest.raises(ValueError):
        HouseholdProfileService.normalise_list(["x" * 61])
    with pytest.raises(ValueError):
        HouseholdProfileService.normalise_list([f"item {i}" for i in range(31)])


CREME_NFC = "cr\u00e8me"
CREME_NFD = "cre\u0300me"


def test_normalise_list_nfc_and_nfd_spellings_are_one_entry(unique_user_fn_scoped: TestUser):
    assert HouseholdProfileService.normalise_list([CREME_NFD, CREME_NFC.upper()]) == [CREME_NFC]

    # add_to with a decomposed spelling joins a stored precomposed one
    service = _service(unique_user_fn_scoped)
    service.create_member(MemberProfileCreate(name="Sam", dislikes=["Cr\u00e8me"]))
    assert service.add_to_member("Sam", "dislikes", [CREME_NFD]).dislikes == ["Cr\u00e8me"]


def test_lengths_count_code_points_and_lone_surrogates_are_refused():
    peanut = "\U0001f95c"  # one code point, two UTF-16 units: the frontend cuts by code points too
    assert HouseholdProfileService.normalise_list(["a" * 59 + peanut]) == ["a" * 59 + peanut]
    assert MemberProfileCreate(name="n" * 59 + peanut).name == "n" * 59 + peanut
    with pytest.raises(ValueError, match="at most 60"):
        HouseholdProfileService.normalise_list(["a" * 60 + peanut])
    with pytest.raises(ValueError, match="incomplete character"):
        HouseholdProfileService.normalise_list(["a" * 59 + "\ud83e"])
    with pytest.raises(ValueError, match="incomplete character"):
        MemberProfileCreate(name="Sam\ud83e")


def test_create_member_stores_normalised_lists(unique_user_fn_scoped: TestUser):
    out = _service(unique_user_fn_scoped).create_member(
        MemberProfileCreate(name="  Sam ", allergies=[" Peanuts", "peanuts", ""], diet=Diet.vegan)
    )
    assert out.name == "Sam"
    assert out.allergies == ["Peanuts"]
    assert out.diet == Diet.vegan
    assert str(out.household_id) == str(unique_user_fn_scoped.household_id)


# ------------------------------------------------------------------ uniqueness rules


def test_name_unique_case_insensitive(unique_user_fn_scoped: TestUser):
    service = _service(unique_user_fn_scoped)
    sam = service.create_member(MemberProfileCreate(name="Sam"))
    other = service.create_member(MemberProfileCreate(name="Alex"))

    with pytest.raises(ProfileConflict):
        service.create_member(MemberProfileCreate(name="  SAM "))
    with pytest.raises(ProfileConflict):
        service.create_member(MemberProfileCreate(name="sam"))
    with pytest.raises(ProfileConflict):
        service.update_member(other.id, MemberProfileUpdate(name="sAm"))

    # renaming a profile to another spelling of its own name is fine
    assert service.update_member(sam.id, MemberProfileUpdate(name="SAM")).name == "SAM"
    assert len(service.get().members) == 2


ZOE_NFC = "Zo\u00e9"
ZOE_NFD = "Zoe\u0301"


def test_name_nfc_and_nfd_spellings_clash(unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    service = _service(user)
    zoe = service.create_member(MemberProfileCreate(name=ZOE_NFD))
    assert zoe.name == ZOE_NFC  # stored normalised

    with pytest.raises(ProfileConflict):
        service.create_member(MemberProfileCreate(name=ZOE_NFC))
    with pytest.raises(ProfileConflict):
        service.create_member(MemberProfileCreate(name=ZOE_NFD.upper()))

    # a row stored as NFD before names were normalised still clashes and is still found by name
    user.repos.session.execute(
        update(HouseholdMemberProfile).where(HouseholdMemberProfile.id == zoe.id).values(name=ZOE_NFD)
    )
    user.repos.session.commit()
    with pytest.raises(ProfileConflict):
        service.create_member(MemberProfileCreate(name=ZOE_NFC))
    assert service.add_to_member(ZOE_NFC, "likes", ["soup"]).likes == ["soup"]


def test_name_at_most_60_characters():
    assert MemberProfileCreate(name="n" * 60).name == "n" * 60
    with pytest.raises(ValueError, match="at most 60"):
        MemberProfileCreate(name="n" * 61)
    with pytest.raises(ValueError, match="at most 60"):
        MemberProfileUpdate(name="n" * 61)
    # trimmed before measuring
    assert MemberProfileCreate(name=f"  {'n' * 60}  ").name == "n" * 60


def test_name_unique_ignores_other_households(unique_user: TestUser, h2_user: TestUser):
    name = f"Shared {random_string(8)}"
    _service(unique_user).create_member(MemberProfileCreate(name=name))
    assert _service(h2_user).create_member(MemberProfileCreate(name=name)).name == name


def test_one_profile_per_user(unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    service = _service(user)
    me = service.create_member(MemberProfileCreate(name="Me", user_id=user.user_id))
    other = service.create_member(MemberProfileCreate(name="Other"))

    with pytest.raises(ProfileConflict):
        service.create_member(MemberProfileCreate(name="Me again", user_id=user.user_id))
    with pytest.raises(ProfileConflict):
        service.update_member(other.id, MemberProfileUpdate(user_id=user.user_id))

    # re-sending a profile's own link is not a conflict; unlinking frees the user
    assert service.update_member(me.id, MemberProfileUpdate(user_id=user.user_id, notes="hi")).notes == "hi"
    service.update_member(me.id, MemberProfileUpdate(user_id=None))
    assert service.update_member(other.id, MemberProfileUpdate(user_id=user.user_id)).user_id == user.user_id
    assert [m.name for m in service.get().members] == ["Me", "Other"]


def test_user_from_another_household_is_refused(unique_user: TestUser, h2_user: TestUser, g2_user: TestUser):
    service = _service(unique_user)
    tag = random_string(8)
    target = service.create_member(MemberProfileCreate(name=f"Target {tag}"))

    for outsider in (h2_user.user_id, g2_user.user_id, uuid4()):
        with pytest.raises(NoEntryFound):
            service.create_member(MemberProfileCreate(name=f"Outsider {tag}", user_id=outsider))
        with pytest.raises(NoEntryFound):
            service.update_member(target.id, MemberProfileUpdate(user_id=outsider))

    assert unique_user.repos.member_profiles.by_name_casefold(f"Outsider {tag}") is None
    fetched = unique_user.repos.member_profiles.get_one(target.id)
    assert fetched is not None and fetched.user_id is None


def test_linking_a_user_of_the_same_household(unique_user_fn_scoped: TestUser):
    extra = _extra_user(unique_user_fn_scoped)
    out = _service(unique_user_fn_scoped).create_member(MemberProfileCreate(name="Partner", user_id=extra))
    assert out.user_id == extra


# ------------------------------------------------------------------ update / delete


def test_partial_update_keeps_omitted_fields(unique_user_fn_scoped: TestUser):
    service = _service(unique_user_fn_scoped)
    created = service.create_member(
        MemberProfileCreate(
            name="Sam",
            is_child=True,
            diet=Diet.vegetarian,
            allergies=["peanuts"],
            exclusions=["pork"],
            dislikes=["mushrooms"],
            likes=["pasta"],
            notes="Picky",
            position=2,
        )
    )

    updated = service.update_member(created.id, MemberProfileUpdate(likes=["soup"]))

    assert updated.likes == ["soup"]
    assert (updated.name, updated.is_child, updated.diet, updated.notes, updated.position) == (
        "Sam",
        True,
        Diet.vegetarian,
        "Picky",
        2,
    )
    assert (updated.allergies, updated.exclusions, updated.dislikes) == (["peanuts"], ["pork"], ["mushrooms"])

    # explicit null clears a nullable field
    assert service.update_member(created.id, MemberProfileUpdate(notes=None)).notes is None


def test_update_and_delete_unknown_member(unique_user_fn_scoped: TestUser):
    service = _service(unique_user_fn_scoped)
    with pytest.raises(NoEntryFound):
        service.update_member(uuid4(), MemberProfileUpdate(likes=["soup"]))
    with pytest.raises(NoEntryFound):
        service.delete_member(uuid4())


def test_delete_member(unique_user_fn_scoped: TestUser):
    service = _service(unique_user_fn_scoped)
    created = service.create_member(MemberProfileCreate(name="Sam"))
    assert service.delete_member(created.id).id == created.id
    assert service.get().members == []


# ------------------------------------------------------------------ add_to


def test_add_to_appends_and_dedupes(unique_user_fn_scoped: TestUser):
    service = _service(unique_user_fn_scoped)
    created = service.create_member(MemberProfileCreate(name="Sam", dislikes=["Olives"], likes=["pasta"]))

    out = service.add_to_member(str(created.id), "dislikes", ["mushrooms", " olives ", "MUSHROOMS", ""])

    assert out.dislikes == ["Olives", "mushrooms"]
    assert out.likes == ["pasta"]
    fetched = unique_user_fn_scoped.repos.member_profiles.get_one(created.id)
    assert fetched is not None and fetched.dislikes == ["Olives", "mushrooms"]


def test_add_to_by_case_insensitive_name(unique_user_fn_scoped: TestUser):
    service = _service(unique_user_fn_scoped)
    created = service.create_member(MemberProfileCreate(name="Émile", allergies=["sesame"]))

    out = service.add_to_member("  émile ", "allergies", ["peanuts"])

    assert out.id == created.id
    assert out.allergies == ["sesame", "peanuts"]


def test_add_to_unknown_member_or_field(unique_user_fn_scoped: TestUser):
    service = _service(unique_user_fn_scoped)
    service.create_member(MemberProfileCreate(name="Sam"))
    with pytest.raises(NoEntryFound):
        service.add_to_member("Nobody", "likes", ["soup"])
    with pytest.raises(NoEntryFound):
        service.add_to_member(str(uuid4()), "likes", ["soup"])
    with pytest.raises(ValueError):
        service.add_to_member("Sam", "notes", ["soup"])  # type: ignore[arg-type]


def test_add_to_enforces_limits_without_writing(unique_user_fn_scoped: TestUser):
    service = _service(unique_user_fn_scoped)
    created = service.create_member(MemberProfileCreate(name="Sam", likes=[f"like {i}" for i in range(29)]))

    with pytest.raises(ValueError):
        service.add_to_member("Sam", "likes", ["one more", "and another"])
    with pytest.raises(ValueError):
        service.add_to_member("Sam", "likes", ["x" * 61])

    fetched = unique_user_fn_scoped.repos.member_profiles.get_one(created.id)
    assert fetched is not None and len(fetched.likes) == 29
    # duplicates do not count towards the limit
    assert len(service.add_to_member("Sam", "likes", ["LIKE 3", "thirtieth"]).likes) == 30


# ------------------------------------------------------------------ preferences


def test_preferences_upsert_creates_then_updates(unique_user_fn_scoped: TestUser):
    service = _service(unique_user_fn_scoped)

    created = service.update_preferences(
        MealPreferencesUpdate(default_servings=4, quick_weekdays=[2, 0], favourite_cuisines=["Thai"])
    )
    assert created.default_servings == 4
    assert created.quick_weekdays == [0, 2]
    assert created.weeknight_max_minutes is None

    updated = service.update_preferences(MealPreferencesUpdate(weeknight_max_minutes=30, notes="No oven"))
    assert updated.id == created.id
    assert updated.weeknight_max_minutes == 30
    assert updated.notes == "No oven"
    # omitted fields are kept
    assert (updated.default_servings, updated.quick_weekdays, updated.favourite_cuisines) == (4, [0, 2], ["Thai"])

    # explicit null clears a nullable field
    assert service.update_preferences(MealPreferencesUpdate(default_servings=None)).default_servings is None


def test_preferences_upsert_with_nothing_set_creates_defaults(unique_user_fn_scoped: TestUser):
    out = _service(unique_user_fn_scoped).update_preferences(MealPreferencesUpdate())
    assert (out.quick_weekdays, out.favourite_cuisines, out.default_servings) == ([], [], None)


# ------------------------------------------------------------------ isolation


def test_other_households_cannot_see_or_change_profiles(unique_user: TestUser, h2_user: TestUser, g2_user: TestUser):
    tag = random_string(8)
    mine = _service(unique_user).create_member(MemberProfileCreate(name=f"Secret {tag}", likes=["pasta"]))
    _service(unique_user).update_preferences(MealPreferencesUpdate(notes=tag))

    for other in (h2_user, g2_user):
        service = _service(other)
        assert mine.id not in {m.id for m in service.get().members}
        prefs = service.get().preferences
        assert prefs is None or prefs.notes != tag
        with pytest.raises(NoEntryFound):
            service.update_member(mine.id, MemberProfileUpdate(likes=["soup"]))
        with pytest.raises(NoEntryFound):
            service.delete_member(mine.id)
        with pytest.raises(NoEntryFound):
            service.add_to_member(str(mine.id), "likes", ["soup"])
        with pytest.raises(NoEntryFound):
            service.add_to_member(f"Secret {tag}", "likes", ["soup"])

    fetched = unique_user.repos.member_profiles.get_one(mine.id)
    assert fetched is not None and fetched.likes == ["pasta"]


# ------------------------------------------------------------------ guards


def test_add_to_refuses_an_ambiguous_name(unique_user_fn_scoped: TestUser):
    """Old data (or the name race) can hold two profiles with the same folded name: never pick one."""
    user = unique_user_fn_scoped
    service = _service(user)
    first = service.create_member(MemberProfileCreate(name="Sam"))
    second = service.create_member(MemberProfileCreate(name="Other"))
    user.repos.session.execute(
        update(HouseholdMemberProfile).where(HouseholdMemberProfile.id == second.id).values(name="SAM ")
    )
    user.repos.session.commit()

    with pytest.raises(ProfileConflict, match="Several members"):
        service.add_to_member("sam", "allergies", ["peanuts"])
    # by id still works, and nothing was written by the refused call
    assert service.add_to_member(str(first.id), "allergies", ["peanuts"]).allergies == ["peanuts"]
    refetched = user.repos.member_profiles.get_one(second.id)
    assert refetched is not None and refetched.allergies == []


def test_service_refuses_repos_not_scoped_to_the_users_household(unique_user: TestUser, h2_user: TestUser):
    private_user = unique_user.repos.users.get_one(unique_user.user_id)
    assert isinstance(private_user, PrivateUser)
    session = unique_user.repos.session
    for repos in (
        get_repositories(session, group_id=unique_user.group_id, household_id=None),
        get_repositories(session, group_id=None, household_id=None),
        h2_user.repos,
    ):
        with pytest.raises(ValueError, match="scoped to the user's household"):
            HouseholdProfileService(repos, private_user)


def test_write_messages_for_integrity_errors(unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    extra = _extra_user(user)
    service = _service(user)
    service.create_member(MemberProfileCreate(name="Linked", user_id=extra))

    # a real lost race on the user-link constraint (the check bypassed) keeps the user-link message
    with pytest.raises(ProfileConflict, match="already linked"):
        service._write(lambda: service.members.create({"name": "Racer", "user_id": extra}))

    def other_violation():
        raise IntegrityError("INSERT ...", {}, Exception('insert violates foreign key constraint "fk_user"'))

    with pytest.raises(ProfileConflict, match="Conflicting profile data") as excinfo:
        service._write(other_violation)
    assert "already linked" not in str(excinfo.value)
    assert [m.name for m in service.get().members] == ["Linked"]
