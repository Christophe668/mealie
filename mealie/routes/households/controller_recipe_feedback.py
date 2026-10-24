from collections.abc import Iterator
from contextlib import contextmanager
from functools import cached_property
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Query, status
from pydantic import UUID4

from mealie.core.exceptions import NoEntryFound
from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.controller import controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.household.recipe_feedback import (
    RecipeFeedbackCreate,
    RecipeFeedbackOut,
    RecipeFeedbackPagination,
    RecipeFeedbackSummary,
)
from mealie.schema.response import ErrorResponse
from mealie.services.claude_context.recipe_feedback_service import RecipeFeedbackService

router = UserAPIRouter(prefix="/households/recipe-feedback", tags=["Households: Recipe Feedback"])

MAX_SUMMARY_IDS = 100


@contextmanager
def _service_errors() -> Iterator[None]:
    """Map the feedback service's `NoEntryFound` (missing or foreign recipe/feedback) to a 404."""
    try:
        yield
    except NoEntryFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message=str(e))) from e


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=ErrorResponse.respond(message=message))


def _parse_recipe_ids(raw: str | None) -> list[UUID]:
    """Comma-separated UUIDs; blanks are ignored, an invalid UUID or more than 100 ids is a 422."""
    parts = [part.strip() for part in (raw or "").split(",") if part.strip()]
    if len(parts) > MAX_SUMMARY_IDS:
        raise _unprocessable(f"At most {MAX_SUMMARY_IDS} recipe ids are allowed.")
    try:
        return [UUID(part) for part in parts]
    except ValueError as e:
        raise _unprocessable("recipeIds must be comma-separated UUIDs.") from e


@controller(router)
class HouseholdRecipeFeedbackController(BaseUserController):
    @cached_property
    def service(self) -> RecipeFeedbackService:
        return RecipeFeedbackService(self.repos, self.user)

    @router.get("", response_model=RecipeFeedbackPagination)
    def get_all(
        self,
        recipe_id: UUID4 | None = Query(None, alias="recipeId"),
        page: int = Query(1, ge=1),
        per_page: int = Query(50, alias="perPage", ge=-1),
    ):
        """The household's feedback, newest `madeOn` first; without `recipeId`, the latest across recipes.

        `perPage=-1` returns everything."""
        response = self.service.list(recipe_id, page, per_page)
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if recipe_id is not None:
            params["recipe_id"] = str(recipe_id)
        response.set_pagination_guides(router.url_path_for("get_all"), params)
        return response

    @router.post("", response_model=RecipeFeedbackOut, status_code=status.HTTP_201_CREATED)
    def create_one(self, data: RecipeFeedbackCreate):
        with _service_errors():
            return self.service.record(data)

    # declared before `/{item_id}` so "summary" is not captured as an id
    @router.get("/summary", response_model=dict[str, RecipeFeedbackSummary])
    def get_summary(self, recipe_ids: str | None = Query(None, alias="recipeIds")):
        """Per-recipe summaries for up to 100 comma-separated recipe ids; recipes without feedback are omitted."""
        ids = _parse_recipe_ids(recipe_ids)
        if not ids:
            return {}
        return {str(recipe_id): summary for recipe_id, summary in self.service.summaries(ids).items()}

    @router.delete("/{item_id}", response_model=RecipeFeedbackOut)
    def delete_one(self, item_id: UUID4):
        with _service_errors():
            return self.service.delete(item_id)
