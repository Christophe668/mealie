from datetime import date
from uuid import UUID

import pytest

from mealie.core.exceptions import NoEntryFound
from mealie.schema.household.group_shopping_list import ShoppingListItemCreate, ShoppingListOut, ShoppingListSave
from mealie.schema.household.pantry import PantryItemCreate, PantryItemUpdate, PantryLocation, PantrySource
from mealie.schema.labels.multi_purpose_label import MultiPurposeLabelSave
from mealie.schema.recipe.recipe_ingredient import IngredientFood, SaveIngredientFood, SaveIngredientUnit
from mealie.services.claude_context.pantry_service import PantryService
from mealie.services.household_services.shopping_lists import ShoppingListService
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

DAY_1 = date(2026, 10, 20)
DAY_2 = date(2026, 10, 24)


def _food(user: TestUser, label_id: UUID | None = None) -> IngredientFood:
    return user.repos.ingredient_foods.create(
        SaveIngredientFood(name=random_string(10), group_id=user.group_id, label_id=label_id)
    )


def _unit_id(user: TestUser) -> UUID:
    return user.repos.ingredient_units.create(SaveIngredientUnit(name=random_string(10), group_id=user.group_id)).id


def _list(user: TestUser) -> ShoppingListOut:
    return user.repos.group_shopping_lists.create(
        ShoppingListSave(name=random_string(8), group_id=user.group_id, user_id=user.user_id)
    )


def _is_on_hand(user: TestUser, food_id: UUID) -> bool:
    """What upstream's shopping-list deduction sees for this food, read fresh from the database."""
    user.repos.session.expire_all()
    shopping_list = _list(user)
    food = user.repos.ingredient_foods.get_one(food_id)
    assert food is not None
    return ShoppingListService(user.repos)._is_on_hand(shopping_list.id, food)


def test_add_merges_same_food(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    food = _food(unique_user)

    first, first_merged = service.add_item(
        PantryItemCreate(name=food.name, food_id=food.id, bought_on=DAY_1, opened_on=DAY_1)
    )
    second, second_merged = service.add_item(PantryItemCreate(name=food.name, food_id=food.id, bought_on=DAY_2))

    assert (first_merged, second_merged) == (False, True)
    assert second.id == first.id
    assert second.bought_on == DAY_2
    assert second.opened_on == DAY_1
    assert [item.id for item in unique_user.repos.pantry_items.by_food(food.id)] == [first.id]


def test_add_merges_same_name_without_food(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    tag = random_string(8)

    first, _ = service.add_item(PantryItemCreate(name=f"{tag} eggs"))
    second, merged = service.add_item(PantryItemCreate(name=f"{tag.upper()} Eggs"))

    assert merged is True
    assert second.id == first.id
    assert second.name == f"{tag} eggs"
    assert len([item for item in service.list_items() if item.name.casefold() == f"{tag} eggs".casefold()]) == 1


def test_merge_adds_quantities_only_with_same_unit(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    grams, kilos = _unit_id(unique_user), _unit_id(unique_user)

    same = _food(unique_user)
    service.add_item(PantryItemCreate(name=same.name, food_id=same.id, quantity=2, unit_id=grams))
    summed, _ = service.add_item(PantryItemCreate(name=same.name, food_id=same.id, quantity=3, unit_id=grams))
    assert summed.quantity == 5
    assert summed.unit_id == grams

    other = _food(unique_user)
    service.add_item(PantryItemCreate(name=other.name, food_id=other.id, quantity=2, unit_id=grams, note="tin"))
    kept, _ = service.add_item(PantryItemCreate(name=other.name, food_id=other.id, quantity=3, unit_id=kilos))
    assert kept.quantity == 2
    assert kept.unit_id == grams
    assert kept.note is not None
    assert kept.note.startswith("tin")
    assert "3" in kept.note


def test_add_marks_food_on_hand(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    food = _food(unique_user)
    assert _is_on_hand(unique_user, food.id) is False

    service.add_item(PantryItemCreate(name=food.name, food_id=food.id))

    assert _is_on_hand(unique_user, food.id) is True


def test_on_hand_kept_while_another_row_exists(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    food = _food(unique_user)
    first, _ = service.add_item(PantryItemCreate(name=food.name, food_id=food.id))
    # a second row for the same food (e.g. one in the freezer), created directly so it does not merge
    unique_user.repos.pantry_items.create(
        PantryItemCreate(name=food.name, food_id=food.id, location=PantryLocation.freezer)
    )

    service.remove_item(first.id)

    assert _is_on_hand(unique_user, food.id) is True


def test_remove_last_row_clears_on_hand(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    food = _food(unique_user)
    item, _ = service.add_item(PantryItemCreate(name=food.name, food_id=food.id))
    assert _is_on_hand(unique_user, food.id) is True

    removed = service.remove_item(item.id)

    assert removed.id == item.id
    assert unique_user.repos.pantry_items.get_one(item.id) is None
    assert _is_on_hand(unique_user, food.id) is False


def test_put_away_moves_checked_items(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    shopping_list = _list(unique_user)
    food = _food(unique_user)
    unit_id = _unit_id(unique_user)
    note_name = f"{random_string(8)} bread"
    items = unique_user.repos.group_shopping_list_item
    with_food = items.create(
        ShoppingListItemCreate(
            shopping_list_id=shopping_list.id, food_id=food.id, unit_id=unit_id, quantity=2, checked=True
        )
    )
    note_only = items.create(
        ShoppingListItemCreate(shopping_list_id=shopping_list.id, note=note_name, quantity=1, checked=True)
    )
    unchecked = items.create(ShoppingListItemCreate(shopping_list_id=shopping_list.id, note="later", checked=False))

    result = service.put_away(shopping_list.id, None, today=DAY_2)

    assert sorted(str(i) for i in result.removed_item_ids) == sorted([str(with_food.id), str(note_only.id)])
    assert result.merged == []
    assert len(result.created) == 2
    for row in result.created:
        assert row.source == PantrySource.shopping
        assert row.bought_on == DAY_2
    by_name = {row.name: row for row in result.created}
    from_food = by_name[food.name]
    assert (from_food.food_id, from_food.unit_id, from_food.quantity) == (food.id, unit_id, 2)
    from_note = by_name[note_name]
    assert (from_note.food_id, from_note.quantity) == (None, 1)

    remaining = unique_user.repos.group_shopping_lists.get_one(shopping_list.id)
    assert remaining is not None
    assert [item.id for item in remaining.list_items] == [unchecked.id]
    assert _is_on_hand(unique_user, food.id) is True


def test_put_away_picks_location_from_label(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    shopping_list = _list(unique_user)
    labels = unique_user.repos.group_multi_purpose_labels
    frozen_label = labels.create(
        MultiPurposeLabelSave(name=f"Produits surgelés {random_string(6)}", group_id=unique_user.group_id)
    )
    meat_label = labels.create(MultiPurposeLabelSave(name=f"Viande {random_string(6)}", group_id=unique_user.group_id))
    produce_label = labels.create(
        MultiPurposeLabelSave(name=f"Produce {random_string(6)}", group_id=unique_user.group_id)
    )
    frozen = _food(unique_user, label_id=frozen_label.id)
    meat = _food(unique_user, label_id=meat_label.id)
    produce = _food(unique_user, label_id=produce_label.id)
    plain = _food(unique_user)
    items = unique_user.repos.group_shopping_list_item
    for food in (frozen, meat, produce, plain):
        items.create(ShoppingListItemCreate(shopping_list_id=shopping_list.id, food_id=food.id, checked=True))

    result = service.put_away(shopping_list.id, None, today=DAY_2)

    locations = {row.name: row.location for row in result.created}
    assert locations == {
        frozen.name: PantryLocation.freezer,
        meat.name: PantryLocation.fridge,
        produce.name: PantryLocation.cupboard,
        plain.name: PantryLocation.cupboard,
    }


def test_put_away_ignores_repeated_ids(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    shopping_list = _list(unique_user)
    food = _food(unique_user)
    item = unique_user.repos.group_shopping_list_item.create(
        ShoppingListItemCreate(shopping_list_id=shopping_list.id, food_id=food.id, quantity=2, checked=True)
    )

    result = service.put_away(shopping_list.id, [item.id, item.id], today=DAY_2)

    assert [row.quantity for row in result.created] == [2]
    assert result.merged == []
    assert [str(i) for i in result.removed_item_ids] == [str(item.id)]


def test_put_away_does_not_note_the_default_quantity(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    name = f"{random_string(8)} bread"
    service.add_item(PantryItemCreate(name=name))
    shopping_list = _list(unique_user)
    unique_user.repos.group_shopping_list_item.create(
        ShoppingListItemCreate(shopping_list_id=shopping_list.id, note=name, checked=True)
    )

    result = service.put_away(shopping_list.id, None, today=DAY_2)

    assert [(row.name, row.quantity, row.note) for row in result.merged] == [(name, None, None)]


def test_put_away_rejects_unchecked_ids(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    shopping_list = _list(unique_user)
    items = unique_user.repos.group_shopping_list_item
    checked = items.create(ShoppingListItemCreate(shopping_list_id=shopping_list.id, note="milk", checked=True))
    unchecked = items.create(ShoppingListItemCreate(shopping_list_id=shopping_list.id, note="jam", checked=False))

    with pytest.raises(ValueError, match="items not checked"):
        service.put_away(shopping_list.id, [checked.id, unchecked.id])

    remaining = unique_user.repos.group_shopping_lists.get_one(shopping_list.id)
    assert remaining is not None
    assert len(remaining.list_items) == 2


def test_put_away_rejects_foreign_list(unique_user: TestUser, h2_user: TestUser):
    service = PantryService(unique_user.repos)
    foreign = _list(h2_user)
    item = h2_user.repos.group_shopping_list_item.create(
        ShoppingListItemCreate(shopping_list_id=foreign.id, note="secret", checked=True)
    )

    with pytest.raises(NoEntryFound):
        service.put_away(foreign.id, None)
    with pytest.raises(NoEntryFound):
        service.put_away(foreign.id, [item.id])

    assert h2_user.repos.group_shopping_list_item.get_one(item.id) is not None


def test_list_survives_deleted_food(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    food = _food(unique_user)
    item, _ = service.add_item(PantryItemCreate(name=food.name, food_id=food.id))

    unique_user.repos.ingredient_foods.delete(food.id)

    # Postgres nulls food_id (ON DELETE SET NULL); SQLite runs without the FK pragma and leaves a
    # dangling id. Either way the row survives with its stored name and no food.
    listed = [row for row in service.list_items() if row.id == item.id]
    assert len(listed) == 1
    assert listed[0].food is None
    assert listed[0].name == food.name


def test_add_rejects_food_or_unit_from_another_group(unique_user: TestUser, g2_user: TestUser):
    service = PantryService(unique_user.repos)
    foreign_food = _food(g2_user)
    foreign_unit = _unit_id(g2_user)

    with pytest.raises(NoEntryFound):
        service.add_item(PantryItemCreate(name=foreign_food.name, food_id=foreign_food.id))
    with pytest.raises(NoEntryFound):
        service.add_item(PantryItemCreate(name=random_string(8), unit_id=foreign_unit))

    assert unique_user.repos.pantry_items.by_name(foreign_food.name) == []


def test_merge_keeps_the_earlier_use_by(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    food = _food(unique_user)
    service.add_item(PantryItemCreate(name=food.name, food_id=food.id, use_by=date(2026, 11, 5)))

    sooner, _ = service.add_item(PantryItemCreate(name=food.name, food_id=food.id, use_by=date(2026, 10, 30)))
    assert sooner.use_by == date(2026, 10, 30)

    kept, _ = service.add_item(PantryItemCreate(name=food.name, food_id=food.id, use_by=date(2026, 11, 9)))
    assert kept.use_by == date(2026, 10, 30)

    undated, _ = service.add_item(PantryItemCreate(name=food.name, food_id=food.id))
    assert undated.use_by == date(2026, 10, 30)


def test_merge_prefers_the_row_in_the_same_location(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    food = _food(unique_user)
    pantry = unique_user.repos.pantry_items
    pantry.create(PantryItemCreate(name=food.name, food_id=food.id, location=PantryLocation.fridge))
    in_freezer = pantry.create(PantryItemCreate(name=food.name, food_id=food.id, location=PantryLocation.freezer))

    merged_into, merged = service.add_item(
        PantryItemCreate(name=food.name, food_id=food.id, location=PantryLocation.freezer, bought_on=DAY_2)
    )

    assert merged is True
    assert merged_into.id == in_freezer.id
    assert merged_into.bought_on == DAY_2


def test_remove_item_whose_food_was_deleted(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    food = _food(unique_user)
    item, _ = service.add_item(PantryItemCreate(name=food.name, food_id=food.id))
    unique_user.repos.ingredient_foods.delete(food.id)

    removed = service.remove_item(item.id)

    assert removed.id == item.id
    assert unique_user.repos.pantry_items.get_one(item.id) is None


def test_update_item_keeps_a_dangling_food_id(unique_user: TestUser):
    service = PantryService(unique_user.repos)
    food = _food(unique_user)
    item, _ = service.add_item(PantryItemCreate(name=food.name, food_id=food.id))
    unique_user.repos.ingredient_foods.delete(food.id)
    unique_user.repos.session.expire_all()
    row = unique_user.repos.pantry_items.get_one(item.id)
    assert row is not None

    # resend the row as the UI would: same (possibly dangling) food_id, one field changed
    data = PantryItemUpdate.model_validate({**row.model_dump(include=set(PantryItemUpdate.model_fields)), "note": "x"})
    updated = service.update_item(item.id, data)

    assert updated.note == "x"
    assert updated.name == food.name


def test_update_rejects_food_or_unit_from_another_group(unique_user: TestUser, g2_user: TestUser):
    service = PantryService(unique_user.repos)
    item, _ = service.add_item(PantryItemCreate(name=random_string(8)))

    with pytest.raises(NoEntryFound):
        service.update_item(item.id, PantryItemUpdate(name=item.name, food_id=_food(g2_user).id))
    with pytest.raises(NoEntryFound):
        service.update_item(item.id, PantryItemUpdate(name=item.name, unit_id=_unit_id(g2_user)))

    row = unique_user.repos.pantry_items.get_one(item.id)
    assert row is not None
    assert (row.food_id, row.unit_id) == (None, None)


def test_update_and_remove_refuse_another_households_row(unique_user: TestUser, h2_user: TestUser):
    service = PantryService(unique_user.repos)
    theirs = h2_user.repos.pantry_items.create(PantryItemCreate(name=random_string(8)))

    with pytest.raises(NoEntryFound):
        service.update_item(theirs.id, PantryItemUpdate(name="mine now"))
    with pytest.raises(NoEntryFound):
        service.remove_item(theirs.id)

    row = h2_user.repos.pantry_items.get_one(theirs.id)
    assert row is not None
    assert row.name == theirs.name
