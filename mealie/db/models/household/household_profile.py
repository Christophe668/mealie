from typing import TYPE_CHECKING

from pydantic import ConfigDict
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint, event, orm, update
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from .._model_base import BaseMixins, SqlAlchemyBase
from .._model_utils.auto_init import auto_init
from .._model_utils.guid import GUID
from ..users.users import User

if TYPE_CHECKING:
    from .household import Household

# Group-scoped query filters (households, members, recipes) must never reach these household-scoped tables, or
# they would leak other households' profiles. Every relationship into them (`Household.member_profiles`,
# `Household.meal_preferences`) is marked `info={"filterable": False}`, which the query filter builder refuses to
# walk; that is the guard, since inherited `created_at`/`update_at` stay filterable. No column here is a
# `FilterableColumn`, and `User` has no back-reference to profiles. A new relationship pointing at these models must
# carry the same flag. Profiles are read through the repositories' own methods instead.


class HouseholdMemberProfile(SqlAlchemyBase, BaseMixins):
    """Someone who eats in the household (a Mealie user or just a name), with their diet and food constraints."""

    __tablename__ = "household_member_profiles"
    # NULL user ids never collide in a unique constraint (SQLite and PostgreSQL alike), so this is "at most one
    # profile per linked user per household" without a partial index.
    __table_args__ = (
        UniqueConstraint("household_id", "user_id", name="household_member_profiles_household_id_user_id_key"),
    )

    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("households.id"), nullable=False, index=True)
    household: Mapped[Household] = orm.relationship("Household", back_populates="member_profiles")

    user_id: Mapped[GUID | None] = mapped_column(GUID, ForeignKey("users.id", ondelete="SET NULL"))

    name: Mapped[str] = mapped_column(String, nullable=False)
    is_child: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    diet: Mapped[str] = mapped_column(String, nullable=False, default="none")
    allergies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    exclusions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    dislikes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    likes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # The relationship is a read-only view of the FK column; never let auto_init build it.
    model_config = ConfigDict(exclude={"household"})

    @auto_init()
    def __init__(self, **_) -> None:
        pass

    @orm.validates("allergies", "exclusions", "dislikes", "likes")
    def _null_list_is_empty(self, _key: str, value: list[str] | None) -> list[str]:
        """A full `MemberProfileUpdate.model_dump()` carries `None` for unsent lists; store them as `[]`."""
        return [] if value is None else value


@event.listens_for(User, "before_delete")
def _unlink_member_profiles(_mapper: orm.Mapper, connection: Connection, target: User) -> None:
    """Clears `user_id` on profiles linked to a user being deleted.

    The FK says `ondelete="SET NULL"`, but Mealie's SQLite runs without `PRAGMA foreign_keys`, so there the profile
    would keep a dangling id, and a backup restore drops rows with dangling FKs, allergies included. Doing it here
    works on every database and needs no back-reference on `User`. It covers every ORM delete of a user (the
    repository's `delete` and `delete_many`); a bulk `DELETE` statement on `users` bypasses it.
    """
    connection.execute(
        update(HouseholdMemberProfile.__table__)
        .where(HouseholdMemberProfile.__table__.c.user_id == target.id)
        .values(user_id=None)
    )


class HouseholdMealPreferences(SqlAlchemyBase, BaseMixins):
    """The household's cooking habits; one row per household, created on first write."""

    __tablename__ = "household_meal_preferences"

    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: Mapped[GUID] = mapped_column(
        GUID, ForeignKey("households.id"), nullable=False, index=True, unique=True
    )
    household: Mapped[Household] = orm.relationship("Household", back_populates="meal_preferences")

    default_servings: Mapped[int | None] = mapped_column(Integer)
    quick_weekdays: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    """0 = Monday."""
    weeknight_max_minutes: Mapped[int | None] = mapped_column(Integer)
    weekend_max_minutes: Mapped[int | None] = mapped_column(Integer)
    favourite_cuisines: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(String)

    model_config = ConfigDict(exclude={"household"})

    @auto_init()
    def __init__(self, **_) -> None:
        pass

    @orm.validates("quick_weekdays", "favourite_cuisines")
    def _null_list_is_empty(self, _key: str, value: list | None) -> list:
        """A full `MealPreferencesUpdate.model_dump()` carries `None` for unsent lists; store them as `[]`."""
        return [] if value is None else value
