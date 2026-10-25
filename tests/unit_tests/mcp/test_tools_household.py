import contextlib
from typing import Any
from uuid import uuid4

import pytest
from mcp.server.auth.provider import AccessToken
from sqlalchemy.orm import Session

from mealie.mcp import auth, context
from mealie.mcp.errors import McpToolError
from mealie.mcp.server import mcp_server
from mealie.mcp.tools.household import get_household_context, update_household_profile
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

SCOPES = ["recipes:read", "household:write"]

MEMBER_KEYS = {
    "id",
    "name",
    "is_child",
    "diet",
    "allergies",
    "exclusions",
    "dislikes",
    "likes",
    "notes",
    "is_current_user",
}
HOUSEHOLD_KEYS = {
    "default_servings",
    "quick_weekdays",
    "weeknight_max_minutes",
    "weekend_max_minutes",
    "favourite_cuisines",
    "notes",
}


def _as_user(monkeypatch: pytest.MonkeyPatch, session: Session, user: TestUser, scopes: list[str] = SCOPES) -> None:
    token = AccessToken(token="t", client_id="c", scopes=scopes, subject=str(user.user_id))
    monkeypatch.setattr(context, "get_access_token", lambda: token)
    monkeypatch.setattr(auth, "get_access_token", lambda: token)
    monkeypatch.setattr(context, "session_factory", lambda: contextlib.nullcontext(session))


def _stored(session: Session, user: TestUser) -> tuple[list[dict[str, Any]], Any]:
    """What is in the database for the user's household: (members as dicts, preferences row or None)."""
    session.expire_all()
    members = [m.model_dump(exclude={"created_at", "updated_at"}) for m in user.repos.member_profiles.ordered()]
    return members, user.repos.meal_preferences.get_for_household()


def _by_name(preferences: dict[str, Any], name: str) -> dict[str, Any]:
    return next(m for m in preferences["members"] if m["name"] == name)


# ---------------------------------------------------------------------- context


@pytest.mark.asyncio
async def test_context_preferences_empty(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user, scopes=["recipes:read"])

    result = await get_household_context()

    assert result["preferences"] == {"members": [], "household": None}
    assert [m["id"] for m in result["members"]] == [str(user.user_id)]
    assert set(result["members"][0]) == {"id", "full_name", "username"}


@pytest.mark.asyncio
async def test_context_shape_with_profiles_and_is_current_user(
    monkeypatch: pytest.MonkeyPatch, session: Session, user_tuple: list[TestUser]
):
    me, partner = user_tuple
    _as_user(monkeypatch, session, me)
    written = await update_household_profile(
        members=[
            {"name": "Me", "user_id": str(me.user_id), "diet": "vegetarian", "allergies": ["Peanuts"]},
            {"name": "Partner", "user_id": str(partner.user_id), "dislikes": ["olives"]},
            {"name": "Kid", "is_child": True, "likes": ["pasta"], "notes": "small portions"},
        ],
        household={"default_servings": 3, "quick_weekdays": [2, 0], "weeknight_max_minutes": 30},
    )
    try:
        result = await get_household_context()
        prefs = result["preferences"]
        assert prefs == written
        assert set(prefs) == {"members", "household"}
        assert all(set(m) == MEMBER_KEYS for m in prefs["members"])
        assert set(prefs["household"]) == HOUSEHOLD_KEYS
        assert prefs["household"]["quick_weekdays"] == [0, 2]
        assert prefs["household"]["default_servings"] == 3
        assert prefs["household"]["weekend_max_minutes"] is None

        mine = _by_name(prefs, "Me")
        assert mine["diet"] == "vegetarian"
        assert mine["allergies"] == ["Peanuts"]
        kid = _by_name(prefs, "Kid")
        assert (kid["is_child"], kid["likes"], kid["notes"]) == (True, ["pasta"], "small portions")
        assert {m["name"]: m["is_current_user"] for m in prefs["members"]} == {
            "Me": True,
            "Partner": False,
            "Kid": False,
        }
        # the Mealie user list is unchanged by profiles
        assert {m["id"] for m in result["members"]} == {str(me.user_id), str(partner.user_id)}
        assert all(set(m) == {"id", "full_name", "username"} for m in result["members"])

        # the same household seen by the partner
        _as_user(monkeypatch, session, partner, scopes=["recipes:read"])
        theirs = (await get_household_context())["preferences"]
        assert {m["name"]: m["is_current_user"] for m in theirs["members"]} == {
            "Me": False,
            "Partner": True,
            "Kid": False,
        }
    finally:
        _as_user(monkeypatch, session, me)
        await update_household_profile(remove_member_ids=[m["id"] for m in written["members"]])


# ---------------------------------------------------------------------- writes


@pytest.mark.asyncio
async def test_create_update_remove(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)

    created = await update_household_profile(
        members=[
            {"name": " Sam ", "diet": "pescatarian", "likes": ["Fish", "fish", " "], "dislikes": ["olives"]},
            {"name": "Alex"},
        ]
    )
    sam = _by_name(created, "Sam")
    alex = _by_name(created, "Alex")
    assert sam["likes"] == ["Fish"]
    assert sam["is_current_user"] is False
    assert alex["diet"] == "none"
    assert created["household"] is None

    # a partial update keeps the fields not sent; a rename frees the old name for a new member in the same call
    updated = await update_household_profile(
        members=[
            {"id": sam["id"], "name": "Samuel", "exclusions": ["pork"], "notes": "no spice"},
            {"name": "sam", "is_child": True},
        ],
        remove_member_ids=[alex["id"]],
    )
    samuel = _by_name(updated, "Samuel")
    assert samuel["id"] == sam["id"]
    assert samuel["exclusions"] == ["pork"]
    assert samuel["likes"] == ["Fish"]
    assert samuel["dislikes"] == ["olives"]
    assert samuel["diet"] == "pescatarian"
    assert samuel["notes"] == "no spice"
    assert _by_name(updated, "sam")["is_child"] is True
    assert alex["id"] not in {m["id"] for m in updated["members"]}

    # household habits: created on first write, then partial; null clears a value
    prefs = await update_household_profile(household={"default_servings": 4, "favourite_cuisines": ["Thai", "thai"]})
    assert prefs["household"]["default_servings"] == 4
    assert prefs["household"]["favourite_cuisines"] == ["Thai"]
    prefs = await update_household_profile(household={"default_servings": None, "weekend_max_minutes": 90})
    assert prefs["household"]["default_servings"] is None
    assert prefs["household"]["weekend_max_minutes"] == 90
    assert prefs["household"]["favourite_cuisines"] == ["Thai"]

    members, stored_prefs = _stored(session, user)
    assert {m["name"] for m in members} == {"sam", "Samuel"}
    assert stored_prefs is not None and stored_prefs.weekend_max_minutes == 90


@pytest.mark.asyncio
async def test_link_member_to_current_user(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    created = await update_household_profile(members=[{"name": "Me"}])
    me = _by_name(created, "Me")
    assert me["is_current_user"] is False

    linked = await update_household_profile(members=[{"id": me["id"], "user_id": str(user.user_id)}])
    assert _by_name(linked, "Me")["is_current_user"] is True

    with pytest.raises(McpToolError, match="already linked"):
        await update_household_profile(members=[{"name": "Me again", "user_id": str(user.user_id)}])

    unlinked = await update_household_profile(members=[{"id": me["id"], "user_id": None}])
    assert _by_name(unlinked, "Me")["is_current_user"] is False


@pytest.mark.asyncio
async def test_add_to_appends_without_replacing(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    created = await update_household_profile(
        members=[{"name": "Sam", "dislikes": ["Olives"], "likes": ["pasta"], "allergies": ["peanuts"]}]
    )
    sam_id = _by_name(created, "Sam")["id"]

    # by name, case-insensitively; duplicates collapse onto the existing spelling
    result = await update_household_profile(
        add_to={"member": "  sam ", "field": "dislikes", "values": ["mushrooms", "olives", " Mushrooms "]}
    )
    sam = _by_name(result, "Sam")
    assert sam["dislikes"] == ["Olives", "mushrooms"]
    assert sam["likes"] == ["pasta"]
    assert sam["allergies"] == ["peanuts"]

    # by id
    result = await update_household_profile(add_to={"member": sam_id, "field": "allergies", "values": ["Sesame"]})
    sam = _by_name(result, "Sam")
    assert sam["allergies"] == ["peanuts", "Sesame"]
    assert sam["dislikes"] == ["Olives", "mushrooms"]

    members, _ = _stored(session, user)
    assert members[0]["dislikes"] == ["Olives", "mushrooms"]
    assert members[0]["allergies"] == ["peanuts", "Sesame"]


@pytest.mark.asyncio
async def test_add_to_member_created_in_the_same_call(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    _as_user(monkeypatch, session, unique_user_fn_scoped)
    result = await update_household_profile(
        members=[{"name": "Kid", "likes": ["pasta"]}],
        add_to={"member": "kid", "field": "likes", "values": ["pizza"]},
    )
    assert _by_name(result, "Kid")["likes"] == ["pasta", "pizza"]


@pytest.mark.asyncio
async def test_nothing_to_change(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser):
    _as_user(monkeypatch, session, unique_user_fn_scoped)
    with pytest.raises(McpToolError, match="nothing to change"):
        await update_household_profile()
    with pytest.raises(McpToolError, match="nothing to change"):
        await update_household_profile(members=[], remove_member_ids=[])


# ---------------------------------------------------------------------- validation before write


def _invalid_cases(sam_id: str, foreign_user_id: str) -> list[tuple[dict[str, Any], str]]:
    """(call kwargs, expected error fragment); each call also carries valid changes that must not be written."""
    return [
        ({"members": [{"name": "Kim", "diet": "carnivore"}]}, r"members\[1\]: diet"),
        ({"members": [{"name": "Kim", "colour": "blue"}]}, r"members\[1\]: unknown key\(s\) colour"),
        ({"members": [{"name": "Kim", "allergies": ["a" * 61]}]}, "60 characters"),
        ({"members": [{"name": "Kim", "likes": [f"item {i}" for i in range(31)]}]}, "at most 30"),
        ({"members": [{"name": "Kim", "notes": "n" * 501}]}, "notes"),
        ({"members": [{"is_child": True}]}, r"members\[1\]: name: Field required"),
        ({"members": [{"name": "   "}]}, "name must not be empty"),
        ({"members": ["Kim"]}, "expected an object"),
        ({"members": [{"name": "SAM"}]}, "a member named 'Sam' already exists"),
        ({"members": [{"name": "Kim"}, {"name": "kim"}]}, "a member named 'Kim' already exists"),
        ({"members": [{"id": str(uuid4()), "likes": ["x"]}]}, "member not found"),
        ({"members": [{"id": "not-an-id", "likes": ["x"]}]}, "member not found: not-an-id"),
        ({"members": [{"id": sam_id, "likes": None}]}, "cannot be null"),
        ({"members": [{"id": sam_id}, {"id": sam_id, "notes": "x"}]}, "repeated id"),
        ({"members": [{"name": "Kim", "user_id": foreign_user_id}]}, "user not found"),
        ({"members": [{"name": "Kim", "user_id": "nope"}]}, "user_id"),
        ({"members": [{"id": sam_id, "notes": "x"}], "remove_member_ids": [sam_id]}, "also in remove_member_ids"),
        ({"remove_member_ids": [str(uuid4())]}, "member not found"),
        ({"remove_member_ids": [sam_id, sam_id]}, "repeated id"),
        ({"household": {"default_servings": 0}}, "household: default_servings"),
        ({"household": {"quick_weekdays": [7]}}, "household: quick_weekdays"),
        ({"household": {"weekend_max_minutes": 1000}}, "household: weekend_max_minutes"),
        ({"household": {"servings": 4}}, r"household: unknown key\(s\) servings"),
        ({"add_to": {"member": "Sam", "field": "diet", "values": ["vegan"]}}, "add_to.field: must be one of"),
        ({"add_to": {"member": "Nobody", "field": "likes", "values": ["x"]}}, "add_to: member not found: Nobody"),
        ({"add_to": {"member": str(uuid4()), "field": "likes", "values": ["x"]}}, "add_to: member not found"),
        ({"add_to": {"member": "Sam", "field": "likes"}}, "add_to: missing values"),
        ({"add_to": {"member": "Sam", "field": "likes", "values": "pizza"}}, "list of strings"),
        ({"add_to": {"member": "Sam", "field": "likes", "values": ["  "]}}, "at least one"),
        ({"add_to": {"member": "Sam", "field": "likes", "values": ["b" * 61]}}, "60 characters"),
        # Sam already has 29 likes
        ({"add_to": {"member": "Sam", "field": "likes", "values": ["new 1", "new 2"]}}, "Sam's likes: at most 30"),
        # Sam is removed earlier in the same call, so add_to cannot reach him
        ({"remove_member_ids": [sam_id], "add_to": {"member": "Sam", "field": "likes", "values": ["x"]}}, "not found"),
    ]


@pytest.mark.asyncio
async def test_invalid_entry_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser, g2_user: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    created = await update_household_profile(
        members=[{"name": "Sam", "likes": [f"like {i}" for i in range(29)], "dislikes": ["olives"]}],
        household={"default_servings": 2},
    )
    sam_id = _by_name(created, "Sam")["id"]
    before = _stored(session, user)

    for kwargs, error in _invalid_cases(sam_id, str(g2_user.user_id)):
        # a valid change of every kind next to the invalid one
        call: dict[str, Any] = {
            "members": [{"name": f"Valid {random_string(6)}", "allergies": ["milk"]}, *kwargs.get("members", [])],
            "household": kwargs.get("household", {"weeknight_max_minutes": 20}),
        }
        if "remove_member_ids" in kwargs:
            call["remove_member_ids"] = kwargs["remove_member_ids"]
        if "add_to" in kwargs:
            call["add_to"] = kwargs["add_to"]
        elif "remove_member_ids" not in kwargs:
            call["add_to"] = {"member": "Sam", "field": "dislikes", "values": ["anchovies"]}

        with pytest.raises(McpToolError, match=error):
            await update_household_profile(**call)
        assert _stored(session, user) == before, (kwargs, error)


@pytest.mark.asyncio
async def test_one_valid_one_invalid_member_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    created = await update_household_profile(members=[{"name": "Sam", "likes": ["pasta"]}])
    sam_id = _by_name(created, "Sam")["id"]
    before = _stored(session, user)

    # the valid update and creation come first in the batch; the invalid entry is last
    with pytest.raises(McpToolError, match=r"members\[2\]: diet"):
        await update_household_profile(
            members=[{"id": sam_id, "likes": ["soup"]}, {"name": "Kim"}, {"name": "Bad", "diet": "carnivore"}],
            household={"default_servings": 4},
        )

    assert _stored(session, user) == before
    assert before[0][0]["likes"] == ["pasta"]
    assert before[1] is None


@pytest.mark.asyncio
async def test_ambiguous_add_to_member_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    # names are unique by a service check only: old data can hold the same name twice
    first = user.repos.member_profiles.create({"name": "Alex"})
    user.repos.member_profiles.create({"name": "alex"})
    _as_user(monkeypatch, session, user)
    before = _stored(session, user)

    with pytest.raises(McpToolError, match="several members are named 'Alex'; use the member id"):
        await update_household_profile(
            members=[{"name": "Kim"}], add_to={"member": "Alex", "field": "allergies", "values": ["nuts"]}
        )
    assert _stored(session, user) == before

    # the id disambiguates
    result = await update_household_profile(add_to={"member": str(first.id), "field": "allergies", "values": ["nuts"]})
    assert next(m for m in result["members"] if m["id"] == str(first.id))["allergies"] == ["nuts"]


# ---------------------------------------------------------------------- scope


@pytest.mark.asyncio
async def test_update_requires_household_write(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user, scopes=["recipes:read", "recipes:write", "pantry:write"])

    with pytest.raises(McpToolError, match="household:write"):
        await update_household_profile(members=[{"name": "Sam"}], household={"default_servings": 2})
    assert _stored(session, user) == ([], None)

    # reading stays available with recipes:read
    assert (await get_household_context())["preferences"] == {"members": [], "household": None}


@pytest.mark.asyncio
async def test_update_schema_advertises_parameters():
    tools = {tool.name: tool for tool in await mcp_server.list_tools()}
    schema = tools["update_household_profile"].input_schema
    assert set(schema["properties"]) == {"members", "remove_member_ids", "household", "add_to"}
    assert not schema.get("required")


# ---------------------------------------------------------------------- isolation


@pytest.mark.asyncio
async def test_profiles_isolated_between_households_and_groups(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    unique_user: TestUser,
    h2_user: TestUser,
    g2_user: TestUser,
):
    name = f"Secret {random_string(8)}"
    _as_user(monkeypatch, session, unique_user)
    created = await update_household_profile(
        members=[{"name": name, "allergies": ["peanuts"]}], household={"notes": "mine"}
    )
    mine = _by_name(created, name)
    try:
        for other in (h2_user, g2_user):
            _as_user(monkeypatch, session, other)
            seen = (await get_household_context())["preferences"]
            assert mine["id"] not in {m["id"] for m in seen["members"]}
            assert seen["household"] is None or seen["household"]["notes"] != "mine"

            with pytest.raises(McpToolError, match="member not found"):
                await update_household_profile(members=[{"id": mine["id"], "allergies": []}])
            with pytest.raises(McpToolError, match="member not found"):
                await update_household_profile(remove_member_ids=[mine["id"]])
            for ref in (mine["id"], name):
                with pytest.raises(McpToolError, match="member not found"):
                    await update_household_profile(add_to={"member": ref, "field": "likes", "values": ["x"]})
            # a user of another household cannot be linked
            with pytest.raises(McpToolError, match="user not found"):
                await update_household_profile(members=[{"name": "Spy", "user_id": str(unique_user.user_id)}])
            assert all(m["name"] != "Spy" for m in (await get_household_context())["preferences"]["members"])

            # the same name is free elsewhere, and writing there does not touch this household
            theirs = await update_household_profile(members=[{"name": name}], household={"notes": "theirs"})
            await update_household_profile(remove_member_ids=[_by_name(theirs, name)["id"]])

        _as_user(monkeypatch, session, unique_user)
        prefs = (await get_household_context())["preferences"]
        assert _by_name(prefs, name)["allergies"] == ["peanuts"]
        assert prefs["household"]["notes"] == "mine"
    finally:
        _as_user(monkeypatch, session, unique_user)
        await update_household_profile(remove_member_ids=[mine["id"]], household={"notes": None})
