"""French text for the TRMNL tonight screen."""

from datetime import date, datetime
from uuid import uuid4

from mealie.schema.household.recipe_feedback import FeedbackVerdict
from mealie.schema.recipe.recipe_ingredient import IngredientUnit
from mealie.services.claude_context.freshness import Freshness, FreshnessStatus
from mealie.services.claude_context.trmnl_format import clock, facts_line, kicker, quantity_text, use_soon_text

ML = IngredientUnit(id=uuid4(), name="millilitre", abbreviation="ml", use_abbreviation=True)
KG = IngredientUnit(id=uuid4(), name="kilogramme", abbreviation="kg", use_abbreviation=True)
BOTTE = IngredientUnit(id=uuid4(), name="botte", abbreviation="bt", use_abbreviation=False)


def test_kicker():
    assert kicker(date(2026, 11, 11)) == "CE SOIR · MERCREDI 11 NOV."
    assert kicker(date(2026, 2, 1)) == "CE SOIR · DIMANCHE 1 FÉVR."
    assert kicker(date(2026, 8, 3)) == "CE SOIR · LUNDI 3 AOÛT"


def test_facts_line_full():
    assert facts_line(2100, 4, FeedbackVerdict.loved) == "35 min · 4 portions · ♥ adoré la dernière fois"


def test_facts_line_drops_missing_and_zero():
    assert facts_line(None, 0, None) == ""
    assert facts_line(0, None, FeedbackVerdict.ok) == "bof la dernière fois"


def test_facts_line_hours_and_singular():
    assert facts_line(4200, 1, FeedbackVerdict.never_again) == "1 h 10 · 1 portion · ✗ pas aimé la dernière fois"
    assert facts_line(3600, 2.5, None) == "1 h · 2,5 portions"


def test_quantity_text():
    assert quantity_text(400.0, ML) == "400 ml"
    assert quantity_text(1.5, KG) == "1,5 kg"
    assert quantity_text(1.25, KG) == "1,3 kg"
    assert quantity_text(2, None) == "2"
    assert quantity_text(1, BOTTE) == "1 botte"
    assert quantity_text(None, BOTTE) == "botte"
    assert quantity_text(0, None) is None


def test_use_soon_text():
    def f(status: FreshnessStatus, days: int | None) -> Freshness:
        return Freshness(status, days, estimated=False, keeps_days=None)

    assert use_soon_text(f(FreshnessStatus.past, -3)) == "dépassé"
    assert use_soon_text(f(FreshnessStatus.check, -1)) == "à vérifier"
    assert use_soon_text(f(FreshnessStatus.soon, 0)) == "aujourd'hui"
    assert use_soon_text(f(FreshnessStatus.soon, 1)) == "1 j"
    assert use_soon_text(f(FreshnessStatus.soon, 2)) == "2 j"


def test_clock():
    assert clock(datetime(2026, 11, 11, 16, 0)) == "16:00"
    assert clock(datetime(2026, 11, 11, 7, 5)) == "07:05"
