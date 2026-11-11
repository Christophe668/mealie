from functools import cached_property

from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.controller import controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.household.trmnl import TrmnlTonightOut
from mealie.services.claude_context.trmnl_service import TrmnlTonightService

router = UserAPIRouter(prefix="/households/trmnl", tags=["Households: TRMNL"])


@controller(router)
class HouseholdTrmnlController(BaseUserController):
    @cached_property
    def service(self) -> TrmnlTonightService:
        return TrmnlTonightService(self.repos, self.user, self.household)

    @router.get("/tonight", response_model=TrmnlTonightOut)
    def tonight(self):
        """Tonight's planned meal and what is missing for it, display-ready for the TRMNL "Ce soir" screen."""
        return self.service.tonight()
