import unicodedata
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import UUID4, ConfigDict, Field, field_validator

from mealie.schema._mealie import MealieModel
from mealie.schema._mealie.mealie_model import UpdatedAtField

MAX_LIST_ITEMS = 30
MAX_ITEM_LENGTH = 60
MAX_NOTES_LENGTH = 500

Notes = Annotated[str, Field(max_length=MAX_NOTES_LENGTH)]
Servings = Annotated[int, Field(ge=1, le=20)]
MaxMinutes = Annotated[int, Field(ge=5, le=480)]
Weekday = Annotated[int, Field(ge=0, le=6)]
"""0 = Monday."""


class Diet(StrEnum):
    none = "none"
    vegetarian = "vegetarian"
    vegan = "vegan"
    pescatarian = "pescatarian"
    halal = "halal"
    kosher = "kosher"
    other = "other"


def _refuse_lone_surrogates(value: str) -> str:
    """A lone UTF-16 surrogate (half an emoji, from a cut made in UTF-16 units) cannot be stored as UTF-8."""
    if any("\ud800" <= char <= "\udfff" for char in value):
        raise ValueError("text contains an incomplete character")
    return value


def normalise_list(values: list[str]) -> list[str]:
    """NFC-normalise, trim, drop empty entries and de-duplicate case-insensitively, keeping the first spelling.

    NFC first, as for names, so "crème" typed precomposed or with a combining accent is one entry. Lengths count code
    points (Python `len`), as the frontend's cut does. Raises `ValueError` when an entry is longer than 60 characters,
    holds a lone surrogate, or more than 30 distinct entries remain.
    """
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = _refuse_lone_surrogates(unicodedata.normalize("NFC", value)).strip()
        if not value:
            continue
        if len(value) > MAX_ITEM_LENGTH:
            raise ValueError(f"each entry must be at most {MAX_ITEM_LENGTH} characters")
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    if len(result) > MAX_LIST_ITEMS:
        raise ValueError(f"at most {MAX_LIST_ITEMS} entries")
    return result


def _refuse_null(value: Any) -> Any:
    """Partial updates may omit a NOT NULL column, but never set it to null.

    Used as an after-validator: pydantic skips it for omitted fields (defaults are not validated).
    """
    if value is None:
        raise ValueError("cannot be null")
    return value


_PROFILE_LISTS = ("allergies", "exclusions", "dislikes", "likes")


MAX_NAME_LENGTH = 60


def name_key(name: str) -> str:
    """The form two member names are compared in: NFC, trimmed, case-folded.

    NFC first so "Zoé" typed with a precomposed "é" and with "e" plus a combining accent are the same name, also
    against rows stored before names were normalised on write.
    """
    return unicodedata.normalize("NFC", name).strip().casefold()


def _clean_name(value: str) -> str:
    value = _refuse_lone_surrogates(unicodedata.normalize("NFC", value)).strip()
    if not value:
        raise ValueError("name must not be empty")
    if len(value) > MAX_NAME_LENGTH:
        raise ValueError(f"name must be at most {MAX_NAME_LENGTH} characters")
    return value


# Normalisation lives on the write schemas only, so a row stored before a rule tightened still loads.


class MemberProfileCreate(MealieModel):
    name: str
    user_id: UUID4 | None = None
    is_child: bool = False
    diet: Diet = Diet.none
    allergies: list[str] = []
    exclusions: list[str] = []
    dislikes: list[str] = []
    likes: list[str] = []
    notes: Notes | None = None
    position: int = Field(default=0, ge=0)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator(*_PROFILE_LISTS)
    @classmethod
    def normalise(cls, values: list[str]) -> list[str]:
        return normalise_list(values)


class MemberProfileUpdate(MealieModel):
    """A partial update: only the fields sent are changed (`model_dump(exclude_unset=True)`)."""

    name: str | None = None
    user_id: UUID4 | None = None
    is_child: bool | None = None
    diet: Diet | None = None
    allergies: list[str] | None = None
    exclusions: list[str] | None = None
    dislikes: list[str] | None = None
    likes: list[str] | None = None
    notes: Notes | None = None
    position: int | None = Field(default=None, ge=0)

    @field_validator("is_child", "diet", "position")
    @classmethod
    def refuse_null(cls, value: Any) -> Any:
        return _refuse_null(value)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str | None) -> str:
        return _clean_name(_refuse_null(value))

    @field_validator(*_PROFILE_LISTS)
    @classmethod
    def normalise(cls, values: list[str] | None) -> list[str]:
        return normalise_list(_refuse_null(values))


class MemberProfileOut(MealieModel):
    id: UUID4
    group_id: UUID4
    household_id: UUID4
    user_id: UUID4 | None = None

    name: str
    is_child: bool = False
    diet: Diet = Diet.none
    allergies: list[str] = []
    exclusions: list[str] = []
    dislikes: list[str] = []
    likes: list[str] = []
    notes: str | None = None
    position: int = 0

    created_at: datetime | None = None
    updated_at: datetime | None = UpdatedAtField(None)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("diet", mode="before")
    @classmethod
    def unknown_diet_is_other(cls, value: Any) -> Any:
        """A stored diet outside the enum (a value dropped later, a hand-edited row, a newer backup) reads as
        `other` instead of failing the whole household's profile."""
        if value is None:
            return Diet.none
        try:
            return Diet(value)
        except ValueError:
            return Diet.other


class MealPreferencesUpdate(MealieModel):
    """A partial update: only the fields sent are changed; nullable fields accept null to clear them."""

    default_servings: Servings | None = None
    quick_weekdays: list[Weekday] | None = None
    weeknight_max_minutes: MaxMinutes | None = None
    weekend_max_minutes: MaxMinutes | None = None
    favourite_cuisines: list[str] | None = None
    notes: Notes | None = None

    @field_validator("quick_weekdays")
    @classmethod
    def unique_sorted_weekdays(cls, values: list[int] | None) -> list[int]:
        return sorted(set(_refuse_null(values)))

    @field_validator("favourite_cuisines")
    @classmethod
    def normalise(cls, values: list[str] | None) -> list[str]:
        return normalise_list(_refuse_null(values))


class MealPreferencesOut(MealieModel):
    id: UUID4
    group_id: UUID4
    household_id: UUID4

    default_servings: int | None = None
    quick_weekdays: list[int] = []
    weeknight_max_minutes: int | None = None
    weekend_max_minutes: int | None = None
    favourite_cuisines: list[str] = []
    notes: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = UpdatedAtField(None)

    model_config = ConfigDict(from_attributes=True)


class HouseholdProfileOut(MealieModel):
    members: list[MemberProfileOut] = []
    preferences: MealPreferencesOut | None = None
