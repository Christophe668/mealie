from datetime import date, datetime
from uuid import UUID

from mealie.core.exceptions import NoEntryFound
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.household.group_shopping_list import ShoppingListItemOut
from mealie.schema.household.pantry import (
    PantryItemCreate,
    PantryItemOut,
    PantryItemUpdate,
    PantryLocation,
    PantrySource,
    PutAwayResult,
)
from mealie.services._base_service import BaseService

# Put-away location rule: `item.label` decides where it goes. Only the item's label is read; when the item has
# none, `ShoppingListItemOut.populate_missing_label` has already filled it from the food's label.
# Matched case-insensitively as substrings, in this order; anything else goes to the cupboard.
# English and French, to cover Mealie's seeded labels in both locales. "Produce" / "Fruits & Légumes"
# is deliberately absent: onions, potatoes and bananas belong in the cupboard.
_FREEZER_LABEL_WORDS = ("frozen", "surgel")
_FRIDGE_LABEL_WORDS = (
    "dairy",
    "fresh",
    "meat",
    "seafood",
    "fish",
    "poultry",
    "frais",
    "laitier",
    "viande",
    "charcuterie",
    "poisson",
    "produits de la mer",
    "volaille",
)


class PantryItemsNotChecked(ValueError):
    """Put away was asked to move shopping items that are not checked."""

    def __init__(self, item_ids: list[str]):
        self.item_ids = item_ids
        super().__init__(f"items not checked: {', '.join(item_ids)}")


_UNNAMED_ITEM = "Unnamed item"  # server-side English fallback: a shopping item with no food, note or display text


def _format_quantity(quantity: float) -> str:
    return f"{quantity:g}"


class PantryService(BaseService):
    """Pantry business rules: the merge rule, on-hand sync and putting the shopping away (spec § 3, § 4)."""

    def __init__(self, repos: AllRepositories):
        self.repos = repos
        self.pantry = repos.pantry_items
        super().__init__()

    # ------------------------------------------------------------------ reads

    def list_items(self, location: PantryLocation | None = None) -> list[PantryItemOut]:
        """Pantry items soonest-to-use first, optionally limited to one location."""
        return self.pantry.ordered(location)

    def _get_or_raise(self, item_id: UUID) -> PantryItemOut:
        item = self.pantry.get_one(item_id)
        if item is None:
            raise NoEntryFound("Pantry item not found.")
        return item

    def _check_references(self, data: PantryItemCreate, existing: PantryItemOut | None = None) -> None:
        """Refuse a food or unit outside this group (the food/unit repositories are group-scoped).

        On an update only changed references are checked: on SQLite a deleted food leaves a dangling
        `food_id` behind, and the row must stay editable without the client clearing it.
        """
        food_id, unit_id = data.food_id, data.unit_id
        if existing is not None:
            food_id = food_id if food_id != existing.food_id else None
            unit_id = unit_id if unit_id != existing.unit_id else None
        if food_id is not None and self.repos.ingredient_foods.get_one(food_id) is None:
            raise NoEntryFound("Food not found.")
        if unit_id is not None and self.repos.ingredient_units.get_one(unit_id) is None:
            raise NoEntryFound("Unit not found.")

    # ------------------------------------------------------------------ writes

    def add_item(self, data: PantryItemCreate) -> tuple[PantryItemOut, bool]:
        """Add an item, merging it into an existing row when the merge rule matches.

        Returns the resulting row and whether it was a merge.
        """
        self._check_references(data)
        existing = self._merge_target(data)
        if existing is None:
            result = self.pantry.create(data)
            merged = False
        else:
            result = self.pantry.update(existing.id, self._merged(existing, data))
            merged = True

        if result.food_id is not None:
            self.sync_on_hand(result.food_id)
        return result, merged

    def update_item(self, item_id: UUID, data: PantryItemUpdate) -> PantryItemOut:
        existing = self._get_or_raise(item_id)
        self._check_references(data, existing)
        updated = self.pantry.update(item_id, data)

        for food_id in {existing.food_id, updated.food_id}:
            if food_id is not None:
                self.sync_on_hand(food_id)
        return updated

    def remove_item(self, item_id: UUID) -> PantryItemOut:
        self._get_or_raise(item_id)
        removed = self.pantry.delete(item_id)

        if removed.food_id is not None:
            self.sync_on_hand(removed.food_id)
        return removed

    def put_away(self, list_id: UUID, item_ids: list[UUID] | None, today: date | None = None) -> PutAwayResult:
        """Move checked shopping items into the pantry, then delete them from the list.

        Order: every pantry row is written first, the shopping items are deleted last. A failure midway
        can leave rows already moved, but it never deletes a shopping item that was not moved.

        `item_ids=None` means every checked item. Raises `NoEntryFound` when the list (or an item on it)
        is not in this household, and `PantryItemsNotChecked` when any requested item is not checked.
        """
        today = today or datetime.now().astimezone().date()
        shopping_list = self.repos.group_shopping_lists.get_one(list_id)
        if shopping_list is None:
            raise NoEntryFound("Shopping list not found.")

        if item_ids is None:
            to_move = [item for item in shopping_list.list_items if item.checked]
        else:
            item_ids = list(dict.fromkeys(item_ids))  # a repeated id must not be put away twice
            on_list = {str(item.id): item for item in shopping_list.list_items}
            missing = [str(item_id) for item_id in item_ids if str(item_id) not in on_list]
            if missing:
                raise NoEntryFound(f"items not on this list: {', '.join(missing)}")
            to_move = [on_list[str(item_id)] for item_id in item_ids]
            unchecked = [str(item.id) for item in to_move if not item.checked]
            if unchecked:
                raise PantryItemsNotChecked(unchecked)

        created: dict[UUID, PantryItemOut] = {}
        merged: dict[UUID, PantryItemOut] = {}
        for item in to_move:
            row, was_merged = self.add_item(self._from_shopping_item(item, today))
            if row.id in created:
                # merged into a row this same put-away created: still a creation, keep its latest state
                created[row.id] = row
            elif was_merged:
                merged[row.id] = row
            else:
                created[row.id] = row

        removed = self.repos.group_shopping_list_item.delete_many([item.id for item in to_move])
        return PutAwayResult(
            created=list(created.values()),
            merged=list(merged.values()),
            removed_item_ids=[item.id for item in removed],
        )

    def sync_on_hand(self, food_id: UUID) -> None:
        """Mirror pantry presence of `food_id` into the household's on-hand foods.

        On hand while at least one pantry row links the food, off otherwise. Only call this for foods a
        pantry change just touched: foods that never had a pantry row keep their manual on-hand mark.
        """
        household_id = self.pantry.household_id
        if household_id is None:
            raise ValueError("PantryService needs household-scoped repositories")

        if self.repos.ingredient_foods.get_one(food_id) is None:
            # deleted (a dangling id on SQLite) or another group's: nothing to sync, its on-hand
            # association rows went with the food
            return
        household = self.repos.households._query_one(household_id)
        food = self.repos.ingredient_foods._query_one(food_id)
        on_hand = household.ingredient_foods_on_hand
        should_be_on_hand = bool(self.pantry.by_food(food_id))

        if should_be_on_hand and food not in on_hand:
            on_hand.append(food)
        elif not should_be_on_hand and food in on_hand:
            on_hand.remove(food)
        else:
            return
        self.repos.session.commit()

    # ------------------------------------------------------------------ helpers

    def _merge_target(self, data: PantryItemCreate) -> PantryItemOut | None:
        """The row an incoming item merges into: same food, or (no food) the same case-folded name.

        With several candidates, the one in the incoming item's location wins, else the oldest.
        """
        candidates = self.pantry.by_food(data.food_id) if data.food_id else self.pantry.by_name(data.name)
        same_place = [row for row in candidates if row.location == data.location]
        if same_place:
            return same_place[0]
        return candidates[0] if candidates else None

    def _merged(self, existing: PantryItemOut, incoming: PantryItemCreate) -> PantryItemUpdate:
        quantity = existing.quantity
        notes = [existing.note] if existing.note else []

        if incoming.quantity is not None:
            if existing.quantity is not None and existing.unit_id == incoming.unit_id:
                quantity = existing.quantity + incoming.quantity
            elif not (incoming.food_id is None and incoming.unit_id is None and incoming.quantity == 1):
                # a bare "1" on a food-less item is the shopping list's default quantity, not information
                notes.append(self._quantity_text(incoming.quantity, incoming.unit_id))
        if incoming.note and incoming.note not in notes:
            notes.append(incoming.note)

        opened = [d for d in (existing.opened_on, incoming.opened_on) if d is not None]
        use_by = [d for d in (existing.use_by, incoming.use_by) if d is not None]
        return PantryItemUpdate(
            name=existing.name,
            food_id=existing.food_id,
            quantity=quantity,
            unit_id=existing.unit_id,
            location=existing.location,
            bought_on=incoming.bought_on or existing.bought_on,
            opened_on=min(opened) if opened else None,
            use_by=min(use_by) if use_by else None,
            source=existing.source,
            note="; ".join(notes) or None,
        )

    def _quantity_text(self, quantity: float, unit_id: UUID | None) -> str:
        unit = self.repos.ingredient_units.get_one(unit_id) if unit_id else None
        return f"{_format_quantity(quantity)} {unit.name}" if unit else _format_quantity(quantity)

    @staticmethod
    def _location_for(item: ShoppingListItemOut) -> PantryLocation:
        label = (item.label.name if item.label else "").casefold()
        if any(word in label for word in _FREEZER_LABEL_WORDS):
            return PantryLocation.freezer
        if any(word in label for word in _FRIDGE_LABEL_WORDS):
            return PantryLocation.fridge
        return PantryLocation.cupboard

    def _from_shopping_item(self, item: ShoppingListItemOut, today: date) -> PantryItemCreate:
        if item.food is not None:
            name, note = item.food.name, item.note or None
        else:
            # a blank shopping item still needs a pantry name (the schema refuses empty names); `display` is not
            # used because for a food-less item it starts with the quantity ("1", "2 kg")
            name, note = (item.note or "").strip() or _UNNAMED_ITEM, None
        quantity = item.quantity
        if item.food is None and item.unit_id is None and quantity == 1:
            # a bare "1" on a food-less item is the shopping list's default quantity, not information
            quantity = None
        return PantryItemCreate(
            name=name,
            # not item.food_id: on SQLite a deleted food leaves a dangling id behind on the shopping item
            food_id=item.food.id if item.food else None,
            quantity=quantity,
            unit_id=item.unit_id,
            location=self._location_for(item),
            bought_on=today,
            source=PantrySource.shopping,
            note=note,
        )
