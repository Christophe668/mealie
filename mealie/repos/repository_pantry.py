from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Select, nulls_last, select

from mealie.db.models.household.pantry import PantryItem
from mealie.schema.household.pantry import PantryItemOut, PantryLocation

from .repository_generic import HouseholdRepositoryGeneric


class RepositoryPantryItems(HouseholdRepositoryGeneric[PantryItemOut, PantryItem]):
    def create(self, data: PantryItemOut | BaseModel | dict) -> PantryItemOut:
        """Create a pantry item, filling `group_id`/`household_id` from the repository scope."""
        values = dict(data) if isinstance(data, dict) else data.model_dump()
        if values.get("group_id") is None:
            values["group_id"] = self.group_id
        if values.get("household_id") is None:
            values["household_id"] = self.household_id
        return super().create(values)

    def _scoped_select(self) -> Select[tuple[PantryItem]]:
        stmt = select(PantryItem).options(*self.schema.loader_options())
        if self.group_id:
            stmt = stmt.filter(PantryItem.group_id == self.group_id)
        if self.household_id:
            stmt = stmt.filter(PantryItem.household_id == self.household_id)
        return stmt

    def _all(self, stmt: Select[tuple[PantryItem]]) -> list[PantryItemOut]:
        return [self.schema.model_validate(row) for row in self.session.execute(stmt).unique().scalars().all()]

    def by_food(self, food_id: UUID) -> list[PantryItemOut]:
        """Pantry items linked to the given food."""
        return self._all(self._scoped_select().filter(PantryItem.food_id == food_id).order_by(PantryItem.created_at))

    def by_name(self, name: str) -> list[PantryItemOut]:
        """Free-text pantry items (no linked food) whose name equals `name`, case-folded.

        Compared in Python because SQLite's `lower()` only folds ASCII ("Crème" != "CRÈME").
        """
        target = name.strip().casefold()
        rows = self._all(self._scoped_select().filter(PantryItem.food_id.is_(None)).order_by(PantryItem.created_at))
        return [row for row in rows if row.name.strip().casefold() == target]

    def ordered(self, location: PantryLocation | None = None) -> list[PantryItemOut]:
        """Pantry items in the default order: `use_by` ascending (nulls last), then `bought_on` descending."""
        stmt = self._scoped_select()
        if location is not None:
            stmt = stmt.filter(PantryItem.location == location.value)
        stmt = stmt.order_by(
            nulls_last(PantryItem.use_by.asc()),
            nulls_last(PantryItem.bought_on.desc()),
            PantryItem.name.asc(),
        )
        return self._all(stmt)
