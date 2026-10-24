from datetime import date, datetime
from enum import StrEnum

from pydantic import UUID4, ConfigDict, Field
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.household.recipe_feedback import RecipeFeedback
from mealie.db.models.recipe import RecipeModel
from mealie.db.models.users import User
from mealie.schema._mealie import MealieModel
from mealie.schema._mealie.mealie_model import UpdatedAtField
from mealie.schema.response.pagination import PaginationBase


class FeedbackVerdict(StrEnum):
    loved = "loved"
    ok = "ok"
    never_again = "never_again"


class RecipeFeedbackCreate(MealieModel):
    recipe_id: UUID4
    verdict: FeedbackVerdict
    effort: int | None = Field(default=None, ge=1, le=3)
    """1 easy, 2 fine, 3 a lot of work."""
    note: str | None = None
    for_whom: str | None = None
    made_on: date | None = None
    """`None` means the household's today, decided by the service."""


class RecipeFeedbackRecipe(MealieModel):
    """The few recipe fields a feedback row carries for lists."""

    id: UUID4
    slug: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class RecipeFeedbackOut(MealieModel):
    """A stored feedback row. `effort` carries no range validator here, so an odd stored effort still loads."""

    id: UUID4
    group_id: UUID4
    household_id: UUID4
    recipe_id: UUID4
    user_id: UUID4 | None = None

    verdict: FeedbackVerdict
    effort: int | None = None
    note: str | None = None
    for_whom: str | None = None
    made_on: date
    timeline_event_id: UUID4 | None = None

    recipe: RecipeFeedbackRecipe
    user_name: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = UpdatedAtField(None)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [
            joinedload(RecipeFeedback.recipe).load_only(RecipeModel.id, RecipeModel.slug, RecipeModel.name),
            joinedload(RecipeFeedback.user).load_only(User.id, User.full_name),
        ]


class RecipeFeedbackPagination(PaginationBase):
    items: list[RecipeFeedbackOut]


class RecipeFeedbackSummary(MealieModel):
    last_verdict: FeedbackVerdict
    last_made_on: date
    loved: int = 0
    ok: int = 0
    never_again: int = 0
    total: int = 0
