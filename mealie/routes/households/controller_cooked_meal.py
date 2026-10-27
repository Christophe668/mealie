from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from functools import cached_property
from uuid import UUID

from fastapi import HTTPException, Query, status
from pydantic import UUID4

from mealie.core.exceptions import NoEntryFound
from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.controller import controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.household.cooked_meal import CookedMealCreate, CookedMealOut, PantryCheckOut
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.schema.response import ErrorResponse
from mealie.services.claude_context.cooked_meal_service import AlreadyCookedError, CookedMealService

router = UserAPIRouter(prefix="/households/cooking", tags=["Households: Cooking"])
# Ticking an entry lives on its own router so the upstream meal plan controller stays untouched.
entry_router = UserAPIRouter(prefix="/households/mealplans", tags=["Households: Cooking"])


@contextmanager
def _service_errors() -> Iterator[None]:
    """Map the cooked meal service's errors: missing → 404, already recorded → 409, any other refusal
    (`ValueError`, e.g. a future date or pantry items not in the recipe) → 400. Messages are passed through."""
    try:
        yield
    except NoEntryFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message=str(e))) from e
    except AlreadyCookedError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=ErrorResponse.respond(message=str(e))) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=ErrorResponse.respond(message=str(e))) from e


def _parse_substitutes(values: list[str]) -> dict[UUID, UUID]:
    """`<reference_id>:<pantry_item_id>` strings as a mapping; a malformed value is a 400."""
    pairs: dict[UUID, UUID] = {}
    for value in values:
        reference, _, item = value.partition(":")
        try:
            key = UUID(reference)
            pairs_item = UUID(item)
        except ValueError as e:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse.respond(message=f"substitute must be <reference_id>:<pantry_item_id>: {value}"),
            ) from e
        if key in pairs:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse.respond(message=f"more than one substitute for ingredient {key}"),
            )
        pairs[key] = pairs_item
    return pairs


class _CookedMealControllerBase(BaseUserController):
    @cached_property
    def service(self) -> CookedMealService:
        return CookedMealService(self.repos, self.user, self.household)


@controller(router)
class HouseholdCookingController(_CookedMealControllerBase):
    @router.get("/{recipe_id}/pantry-check", response_model=PantryCheckOut)
    def pantry_check(
        self,
        recipe_id: UUID4,
        cooked_on: date,
        scale: float | None = Query(None, gt=0, allow_inf_nan=False),
        substitute: list[str] = Query([]),
    ):
        """`scale`: positive and finite. `substitute`: `<reference_id>:<pantry_item_id>`, repeatable; the item stands
        in for that ingredient."""
        with _service_errors():
            return self.service.pantry_check(recipe_id, cooked_on, scale, _parse_substitutes(substitute))

    @router.post("", response_model=CookedMealOut, status_code=status.HTTP_201_CREATED)
    def record(self, data: CookedMealCreate, amend: bool = False):
        """`amend`: told later, so a cooking already recorded gets the pantry, leftovers and feedback added."""
        with _service_errors():
            return self.service.record(data, amend=amend)


@controller(entry_router)
class HouseholdMealplanCookedController(_CookedMealControllerBase):
    @entry_router.post("/{item_id}/cooked", response_model=CookedMealOut)
    def mark_cooked(self, item_id: int, cooked_on: date):
        with _service_errors():
            return self.service.mark_entry(item_id, cooked_on)

    @entry_router.delete("/{item_id}/cooked", response_model=ReadPlanEntry)
    def unmark_cooked(self, item_id: int):
        with _service_errors():
            return self.service.uncook_entry(item_id)
