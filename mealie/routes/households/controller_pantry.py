from collections.abc import Iterator
from contextlib import contextmanager
from functools import cached_property
from math import ceil

from fastapi import Depends, HTTPException, Response, status
from pydantic import UUID4

from mealie.core.exceptions import NoEntryFound
from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.controller import controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.household.pantry import (
    PantryItemCreate,
    PantryItemOut,
    PantryItemPagination,
    PantryItemUpdate,
    PantryLocation,
    PutAwayRequest,
    PutAwayResult,
)
from mealie.schema.response import ErrorResponse
from mealie.schema.response.pagination import OrderByNullPosition, PaginationQuery
from mealie.services.claude_context.pantry_service import PantryService

router = UserAPIRouter(prefix="/households/pantry", tags=["Households: Pantry"])
# Put-away lives on its own router so the upstream shopping list controller stays untouched.
put_away_router = UserAPIRouter(prefix="/households/shopping/lists", tags=["Households: Pantry"])

# The service's default order, spelled for the generic paginator (used when a query filter is given).
_DEFAULT_ORDER_BY = "use_by:asc, bought_on:desc, name:asc"


@contextmanager
def _service_errors() -> Iterator[None]:
    """Map the pantry service's exceptions to HTTP errors: missing → 404, invalid request → 422."""
    try:
        yield
    except NoEntryFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message=str(e))) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=ErrorResponse.respond(message=str(e))) from e


class _PantryControllerBase(BaseUserController):
    @cached_property
    def service(self) -> PantryService:
        return PantryService(self.repos)


@controller(router)
class HouseholdPantryController(_PantryControllerBase):
    @router.get("", response_model=PantryItemPagination)
    def get_all(self, q: PaginationQuery = Depends(PaginationQuery), location: PantryLocation | None = None):
        if q.order_by or q.query_filter:
            response = self._page_with_filters(q, location)
        else:
            response = self._page_in_default_order(q, location)

        params = q.model_dump()
        if location is not None:
            params["location"] = location.value
        response.set_pagination_guides(router.url_path_for("get_all"), params)
        return response

    def _page_in_default_order(self, q: PaginationQuery, location: PantryLocation | None) -> PantryItemPagination:
        items = self.service.list_items(location)
        total = len(items)
        per_page = total if q.per_page == -1 else q.per_page
        total_pages = ceil(total / per_page) if per_page > 0 else 0
        page = total_pages if q.page == -1 else q.page
        page = max(page, 1)
        start = (page - 1) * per_page
        return PantryItemPagination(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
            items=items[start : start + per_page],
        )

    def _page_with_filters(self, q: PaginationQuery, location: PantryLocation | None) -> PantryItemPagination:
        query = q.model_copy()
        if location is not None:
            location_filter = f'location = "{location.value}"'
            query.query_filter = (
                f"({query.query_filter}) AND {location_filter}" if query.query_filter else location_filter
            )
        if not query.order_by:
            query.order_by = _DEFAULT_ORDER_BY
            query.order_by_null_position = OrderByNullPosition.last
        return self.repos.pantry_items.page_all(pagination=query, override=PantryItemOut)  # type: ignore[return-value]

    @router.post("", response_model=PantryItemOut, status_code=status.HTTP_201_CREATED)
    def create_one(self, data: PantryItemCreate, response: Response):
        with _service_errors():
            item, merged = self.service.add_item(data)
        if merged:
            response.status_code = status.HTTP_200_OK
        return item

    @router.get("/{item_id}", response_model=PantryItemOut)
    def get_one(self, item_id: UUID4):
        item = self.repos.pantry_items.get_one(item_id)
        if item is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message="Pantry item not found.")
            )
        return item

    @router.put("/{item_id}", response_model=PantryItemOut)
    def update_one(self, item_id: UUID4, data: PantryItemUpdate):
        with _service_errors():
            return self.service.update_item(item_id, data)

    @router.delete("/{item_id}", response_model=PantryItemOut)
    def delete_one(self, item_id: UUID4):
        with _service_errors():
            return self.service.remove_item(item_id)


@controller(put_away_router)
class HouseholdPutAwayController(_PantryControllerBase):
    @put_away_router.post("/{list_id}/put-away", response_model=PutAwayResult)
    def put_away(self, list_id: UUID4, data: PutAwayRequest):
        with _service_errors():
            return self.service.put_away(list_id, data.item_ids)
