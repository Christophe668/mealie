"""The server copy of the pantry freshness rule (frontend/app/lib/pantry/freshness.ts), same cases."""

from datetime import date, timedelta
from uuid import uuid4

from mealie.schema.household.pantry import PantryItemOut, PantryShelfLife
from mealie.services.claude_context.freshness import NEEDS_ATTENTION, Freshness, FreshnessStatus, freshness_of

TODAY = date(2026, 10, 24)


def _item(
    keeps: tuple[int | None, int | None] | None = None,
    name: str = "Truc",
    **dates: date,
) -> PantryItemOut:
    item = PantryItemOut(id=uuid4(), group_id=uuid4(), household_id=uuid4(), name=name, **dates)
    if keeps is None:
        return item  # keeping time from the built-in table ("Truc" has none)
    # model_copy skips the validator that recomputes the shelf life from the name.
    return item.model_copy(
        update={"shelf_life": PantryShelfLife(opened_days=keeps[0], unopened_days=keeps[1], source="typical")}
    )


def test_use_by_wins_over_estimate():
    f = freshness_of(_item((2, 2), use_by=date(2026, 10, 30), bought_on=date(2026, 10, 1)), TODAY)
    assert f == Freshness(status=FreshnessStatus.ok, days_left=6, estimated=False, keeps_days=None)


def test_use_by_past():
    f = freshness_of(_item(use_by=TODAY - timedelta(days=1)), TODAY)
    assert (f.status, f.days_left, f.estimated) == (FreshnessStatus.past, -1, False)


def test_use_by_soon_boundary():
    assert freshness_of(_item(use_by=TODAY + timedelta(days=2)), TODAY).status == FreshnessStatus.soon
    assert freshness_of(_item(use_by=TODAY + timedelta(days=3)), TODAY).status == FreshnessStatus.ok
    assert freshness_of(_item(use_by=TODAY), TODAY).status == FreshnessStatus.soon


def test_opened_counts_from_opening():
    f = freshness_of(_item((7, 60), bought_on=date(2026, 10, 10), opened_on=date(2026, 10, 16)), TODAY)
    assert f == Freshness(status=FreshnessStatus.check, days_left=-1, estimated=True, keeps_days=7)


def test_estimate_from_opened():
    f = freshness_of(_item((4, 7), opened_on=TODAY - timedelta(days=3)), TODAY)
    assert f == Freshness(status=FreshnessStatus.soon, days_left=1, estimated=True, keeps_days=4)


def test_sealed_counts_from_purchase():
    assert freshness_of(_item((4, 7), bought_on=date(2026, 10, 20)), TODAY).status == FreshnessStatus.ok


def test_well_past_estimate_is_past():
    f = freshness_of(_item((2, 2), bought_on=date(2026, 10, 18)), TODAY)
    assert (f.status, f.days_left) == (FreshnessStatus.past, -4)


def test_estimate_check_then_past():
    # keeps 4: past from -max(2, ceil(4/2)) = -2.
    assert freshness_of(_item((4, 4), bought_on=TODAY - timedelta(days=5)), TODAY).status == FreshnessStatus.check
    assert freshness_of(_item((4, 4), bought_on=TODAY - timedelta(days=6)), TODAY).status == FreshnessStatus.past


def test_short_lived_soon():
    assert freshness_of(_item((2, 2), bought_on=date(2026, 10, 23)), TODAY).status == FreshnessStatus.soon
    assert freshness_of(_item((2, 2), bought_on=date(2026, 10, 24)), TODAY).status == FreshnessStatus.ok


def test_no_dates_or_no_keeping_time_unknown():
    f = freshness_of(_item((3, 21)), TODAY)
    assert f == Freshness(status=FreshnessStatus.unknown, days_left=None, estimated=False, keeps_days=None)
    assert freshness_of(_item(bought_on=date(2026, 1, 1)), TODAY).status == FreshnessStatus.unknown


def test_opened_without_opened_keeping_falls_back_to_purchase():
    f = freshness_of(_item((None, 3), bought_on=date(2026, 10, 20), opened_on=date(2026, 10, 21)), TODAY)
    assert f.status == FreshnessStatus.check


def test_built_in_table_used():
    # "Lait" keeps 4 days once opened in the built-in table.
    f = freshness_of(_item(name="Lait", opened_on=TODAY - timedelta(days=3)), TODAY)
    assert (f.status, f.keeps_days) == (FreshnessStatus.soon, 4)


def test_needs_attention():
    assert NEEDS_ATTENTION == (FreshnessStatus.past, FreshnessStatus.check, FreshnessStatus.soon)
