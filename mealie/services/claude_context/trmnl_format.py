"""French text for the TRMNL "Ce soir" screen. Screen strings, not UI strings: kept here, not in locale files."""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from mealie.schema.household.recipe_feedback import FeedbackVerdict
from mealie.schema.recipe.recipe_ingredient import IngredientUnit
from mealie.services.claude_context.freshness import Freshness, FreshnessStatus

_DAYS = ("LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE")
_MONTHS = ("JANV.", "FÉVR.", "MARS", "AVR.", "MAI", "JUIN", "JUIL.", "AOÛT", "SEPT.", "OCT.", "NOV.", "DÉC.")
_VERDICTS = {
    FeedbackVerdict.loved: "♥ adoré la dernière fois",
    FeedbackVerdict.ok: "bof la dernière fois",
    FeedbackVerdict.never_again: "✗ pas aimé la dernière fois",
}


def kicker(day: date) -> str:
    return f"CE SOIR · {_DAYS[day.weekday()]} {day.day} {_MONTHS[day.month - 1]}"


def number(value: float) -> str:
    """At most one decimal, French comma, no trailing ",0"."""
    rounded = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    text = f"{rounded:f}".removesuffix(".0")
    return text.replace(".", ",")


def _duration(total_seconds: int) -> str:
    minutes = round(total_seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d}" if rest else f"{hours} h"


def facts_line(total_seconds: int | None, servings: float | None, verdict: FeedbackVerdict | None) -> str:
    parts: list[str] = []
    if total_seconds and round(total_seconds / 60) > 0:
        parts.append(_duration(total_seconds))
    if servings and servings > 0:
        parts.append(f"{number(servings)} portion{'' if servings == 1 else 's'}")
    if verdict:
        parts.append(_VERDICTS[verdict])
    return " · ".join(parts)


def unit_text(unit: IngredientUnit) -> str:
    return unit.abbreviation if unit.use_abbreviation and unit.abbreviation else unit.name


def quantity_text(quantity: float | None, unit: IngredientUnit | None) -> str | None:
    if not quantity:
        return unit_text(unit) if unit else None
    amount = number(quantity)
    return f"{amount} {unit_text(unit)}" if unit else amount


def use_soon_text(f: Freshness) -> str:
    if f.status == FreshnessStatus.past:
        return "dépassé"
    if f.status == FreshnessStatus.check or f.days_left is None:
        return "à vérifier"
    return "aujourd'hui" if f.days_left <= 0 else f"{f.days_left} j"


def clock(now: datetime) -> str:
    return now.strftime("%H:%M")
