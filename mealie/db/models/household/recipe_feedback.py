import datetime
from typing import TYPE_CHECKING

from pydantic import ConfigDict
from sqlalchemy import Date, ForeignKey, Integer, String, orm
from sqlalchemy.orm import Mapped, mapped_column

from .._model_base import BaseMixins, FilterableColumn, SqlAlchemyBase
from .._model_utils.auto_init import auto_init
from .._model_utils.guid import GUID

if TYPE_CHECKING:
    from ..recipe import RecipeModel
    from ..users import User
    from .household import Household


class RecipeFeedback(SqlAlchemyBase, BaseMixins):
    """How a cooked recipe went for the household: a verdict, optional effort and note."""

    __tablename__ = "recipe_feedback"

    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("households.id"), nullable=False, index=True)
    household: Mapped[Household] = orm.relationship("Household", back_populates="recipe_feedback")

    recipe_id: FilterableColumn[GUID] = mapped_column(
        GUID, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipe: Mapped[RecipeModel] = orm.relationship("RecipeModel", back_populates="feedback")

    user_id: FilterableColumn[GUID | None] = mapped_column(GUID, ForeignKey("users.id", ondelete="SET NULL"))
    user: Mapped[User | None] = orm.relationship("User", foreign_keys=[user_id])

    for_whom: FilterableColumn[str | None] = mapped_column(String)
    made_on: FilterableColumn[datetime.date] = mapped_column(Date, nullable=False)
    verdict: FilterableColumn[str] = mapped_column(String, nullable=False)
    effort: FilterableColumn[int | None] = mapped_column(Integer)
    note: FilterableColumn[str | None] = mapped_column(String)

    timeline_event_id: FilterableColumn[GUID | None] = mapped_column(
        GUID, ForeignKey("recipe_timeline_events.id", ondelete="SET NULL")
    )

    # Relationships are read-only views of the FK columns; never let auto_init build them.
    model_config = ConfigDict(exclude={"household", "recipe", "user"})

    @auto_init()
    def __init__(self, **_) -> None:
        pass

    @property
    def user_name(self) -> str | None:
        """The recording user's full name; `None` once that user is gone."""
        return self.user.full_name if self.user is not None else None
