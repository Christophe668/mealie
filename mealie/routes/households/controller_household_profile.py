from collections.abc import Iterator
from contextlib import contextmanager
from functools import cached_property

from fastapi import HTTPException, status
from pydantic import UUID4

from mealie.core.exceptions import NoEntryFound
from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.controller import controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.household.household_profile import (
    HouseholdProfileOut,
    MealPreferencesOut,
    MealPreferencesUpdate,
    MemberProfileCreate,
    MemberProfileOut,
    MemberProfileUpdate,
)
from mealie.schema.response import ErrorResponse
from mealie.services.claude_context.household_profile_service import HouseholdProfileService, ProfileConflict

router = UserAPIRouter(prefix="/households/profile", tags=["Households: Profile"])


@contextmanager
def _service_errors() -> Iterator[None]:
    """Map the profile service's errors: `NoEntryFound` (missing or foreign member, or a linked user outside the
    household) to a 404, `ProfileConflict` (duplicate name, user already linked) to a 409."""
    try:
        yield
    except NoEntryFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message=str(e))) from e
    except ProfileConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=ErrorResponse.respond(message=str(e))) from e


@controller(router)
class HouseholdProfileController(BaseUserController):
    @cached_property
    def service(self) -> HouseholdProfileService:
        return HouseholdProfileService(self.repos, self.user)

    @router.get("", response_model=HouseholdProfileOut)
    def get_profile(self):
        """The household's member profiles in display order and its meal preferences (`null` until first saved)."""
        return self.service.get()

    @router.post("/members", response_model=MemberProfileOut, status_code=status.HTTP_201_CREATED)
    def create_member(self, data: MemberProfileCreate):
        with _service_errors():
            return self.service.create_member(data)

    @router.put("/members/{item_id}", response_model=MemberProfileOut)
    def update_member(self, item_id: UUID4, data: MemberProfileUpdate):
        """A partial update: only the fields sent change."""
        with _service_errors():
            return self.service.update_member(item_id, data)

    @router.delete("/members/{item_id}", response_model=MemberProfileOut)
    def delete_member(self, item_id: UUID4):
        with _service_errors():
            return self.service.delete_member(item_id)

    @router.put("/preferences", response_model=MealPreferencesOut)
    def update_preferences(self, data: MealPreferencesUpdate):
        """Creates the household's preferences on first save, otherwise updates only the fields sent."""
        return self.service.update_preferences(data)
