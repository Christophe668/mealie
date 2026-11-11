"""How fresh a pantry item is: past it, worth checking, use soon, fine, or no way to tell.

A copy of the frontend's rule (`frontend/app/lib/pantry/freshness.ts`, `freshnessOf`) for server-side
screens such as the TRMNL one. Keep the two in step.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from mealie.schema.household.pantry import PantryItemOut

USE_BY_URGENT_DAYS = 2
"""A use-by date this many days away (or nearer, or past) is urgent."""


class FreshnessStatus(StrEnum):
    past = "past"
    check = "check"
    soon = "soon"
    ok = "ok"
    unknown = "unknown"


NEEDS_ATTENTION: tuple[FreshnessStatus, ...] = (FreshnessStatus.past, FreshnessStatus.check, FreshnessStatus.soon)
"""Statuses that ask for attention, worst first."""


@dataclass(frozen=True)
class Freshness:
    status: FreshnessStatus
    days_left: int | None
    """Days until the use-by date (or the estimated one); negative once past. None when unknown."""
    estimated: bool
    """True when the date is estimated from the keeping time, False for the item's own use-by date."""
    keeps_days: int | None
    """The typical keeping time the estimate used, in days."""


def _status(days_left: int, keeps_days: int | None) -> FreshnessStatus:
    if keeps_days is None:
        # A real use-by date: past means past.
        if days_left < 0:
            return FreshnessStatus.past
        return FreshnessStatus.soon if days_left <= USE_BY_URGENT_DAYS else FreshnessStatus.ok
    # An estimate: only "probably past" once well beyond it (half its keeping time, two days at least);
    # just beyond it is worth a look. Short-lived foods are "use soon" from halfway.
    if days_left <= -max(2, math.ceil(keeps_days / 2)):
        return FreshnessStatus.past
    if days_left < 0:
        return FreshnessStatus.check
    return FreshnessStatus.soon if days_left <= min(USE_BY_URGENT_DAYS, keeps_days // 2) else FreshnessStatus.ok


def freshness_of(item: PantryItemOut, today: date) -> Freshness:
    if item.use_by:
        days_left = (item.use_by - today).days
        return Freshness(_status(days_left, None), days_left, estimated=False, keeps_days=None)
    life = item.shelf_life
    start: tuple[date, int] | None = None
    if item.opened_on and life and life.opened_days:
        start = (item.opened_on, life.opened_days)
    elif item.bought_on and life and life.unopened_days:
        start = (item.bought_on, life.unopened_days)
    if start is None:
        return Freshness(FreshnessStatus.unknown, None, estimated=False, keeps_days=None)
    days_left = (start[0] + timedelta(days=start[1]) - today).days
    return Freshness(_status(days_left, start[1]), days_left, estimated=True, keeps_days=start[1])
