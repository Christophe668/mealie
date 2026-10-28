import re
from uuid import UUID

from pint import Quantity

from mealie.schema.household.cooked_meal import PantryProposal, ProposalReason, ProposedOutcome
from mealie.schema.household.pantry import PantryItemOut
from mealie.schema.recipe.recipe_ingredient import CreateIngredientUnit, IngredientFood, RecipeIngredient
from mealie.services.parser_services.parser_utils.unit_utils import UnitConverter

SMALL_AMOUNT_RATIO = 0.05
"""A recipe that takes less than this share of a pantry item leaves its quantity alone."""

_EPSILON = 1e-9
# a number not part of a fraction's denominator (`1/2 kg` is half a kilo, never 2 kg), optionally `a/b`
_WEIGHT_IN_NOTE = re.compile(r"(?<![\d/.,])(\d+(?:[.,]\d+)?)(?:\s*/\s*(\d+))?\s*(kg|g)\b")
_EACH_IN_NOTE = re.compile(r"\b(chacune?|each)\b|\b(la|par)\s+pi[eè]ce\b", re.IGNORECASE)

# pint reads these as units nobody means in a recipe: a "bag" is a mass unit, "t" a metric ton
_NOT_UNITS = frozenset({"bag", "t"})
_UNIT_DIMENSIONS = ("[mass]", "[length] ** 3")

# Most derived first: when lines mix, the reason returned is the first of these that any line used.
_REASON_PRECEDENCE = (
    ProposalReason.weight_from_food,
    ProposalReason.weight_from_note,
    ProposalReason.converted,
    ProposalReason.subtracted,
)


def weight_from_note(note: str | None) -> float | None:
    """Grams from the first `200 g` / `1,5 kg` / `1/2 kg` in an ingredient's note, if any."""
    if not note:
        return None

    match = _WEIGHT_IN_NOTE.search(note)
    if not match:
        return None

    amount = float(match.group(1).replace(",", "."))
    if match.group(2) is not None:
        denominator = int(match.group(2))
        if not denominator:
            return None
        amount /= denominator
    return amount * 1000 if match.group(3) == "kg" else amount


def note_weight_is_each(note: str | None) -> bool:
    """Whether the note gives its weight per piece: `150 g chacune`, `each`, `la pièce`, `par pièce`."""
    return bool(note and _EACH_IN_NOTE.search(note))


def grams_each(food: IngredientFood | None) -> float | None:
    """What one piece of the food weighs, from its `grams_each` extra."""
    if food is None or not food.extras:
        return None

    try:
        grams = float(food.extras["grams_each"])
    except KeyError, TypeError, ValueError:
        return None

    return grams if grams > 0 else None


def _as_quantity(text: str, converter: UnitConverter) -> Quantity | None:
    """One of the unit `text` names, as pint reads it, when that is a weight or a volume; `None` otherwise.

    pint answers confidently for many words that aren't kitchen units ("c" is the speed of light, "pinch" a
    picoinch), so anything that isn't a mass or a volume is no answer at all.
    """
    text = text.strip()
    if not text or text.casefold() in _NOT_UNITS:
        return None
    parsed = converter.parse(text)
    if isinstance(parsed, str):
        return None
    quantity = 1 * parsed
    return quantity if quantity.dimensionality in _UNIT_DIMENSIONS else None


def _unit_quantity(unit: CreateIngredientUnit, converter: UnitConverter) -> Quantity | None:
    """What one of this unit is, as a pint quantity of weight or volume; `None` when pint has no idea."""
    if unit.standard_quantity and unit.standard_unit:
        standard = _as_quantity(unit.standard_unit, converter)
        return unit.standard_quantity * standard if standard is not None else None

    for text in (unit.abbreviation, unit.name, unit.plural_name):
        if text and (quantity := _as_quantity(text, converter)) is not None:
            return quantity

    return None


def _is_mass(quantity: Quantity) -> bool:
    return quantity.dimensionality == "[mass]"


def _line_amount(
    line: RecipeIngredient, item: PantryItemOut, scale: float, converter: UnitConverter
) -> tuple[float, ProposalReason] | None:
    """What one line takes, in the item's unit; `None` when it can't be worked out."""
    quantity = (line.quantity or 0) * scale
    line_unit, item_unit = line.unit, item.unit

    if (line_unit is None and item_unit is None) or (
        line_unit is not None and item_unit is not None and line_unit.id is not None and line_unit.id == item_unit.id
    ):
        return quantity, ProposalReason.subtracted

    line_q = _unit_quantity(line_unit, converter) if line_unit else None
    item_q = _unit_quantity(item_unit, converter) if item_unit else None

    if line_q is not None and item_q is not None:
        if not line_q.is_compatible_with(item_q):
            return None
        return float((quantity * line_q / item_q).to("dimensionless").magnitude), ProposalReason.converted

    if line_unit is None and item_q is not None and _is_mass(item_q):
        # pieces into weight: the note's weight is per piece for one piece or when it says so ("chacune"), else
        # it is what all the pieces weigh ("4 pommes de terre, environ 800 g")
        note_grams = weight_from_note(line.note)
        if note_grams is not None:
            per_line = note_grams * (quantity if line.quantity == 1 or note_weight_is_each(line.note) else scale)
            grams = per_line * converter.ureg.gram
            return float((grams / item_q).to("dimensionless").magnitude), ProposalReason.weight_from_note
        per_piece = grams_each(line.food)
        if per_piece is None:
            return None
        grams = quantity * per_piece * converter.ureg.gram
        return float((grams / item_q).to("dimensionless").magnitude), ProposalReason.weight_from_food

    if item_unit is None and line_q is not None and _is_mass(line_q):
        # weight into pieces
        per_piece = grams_each(line.food)
        if per_piece is None:
            return None
        grams = quantity * line_q
        return float((grams / (per_piece * converter.ureg.gram)).to("dimensionless").magnitude), (
            ProposalReason.weight_from_food
        )

    return None


def amount_in_item(
    lines: list[RecipeIngredient], item: PantryItemOut, scale: float
) -> tuple[float | None, ProposalReason]:
    """What the recipe's lines take from this pantry item, in the item's unit, and how that was worked out."""
    if not item.quantity:
        return None, ProposalReason.no_quantity

    converter = UnitConverter()
    total = 0.0
    reasons: set[ProposalReason] = set()
    for line in lines:
        if not line.quantity:
            continue

        amount = _line_amount(line, item, scale, converter)
        if amount is None:
            return None, ProposalReason.units_differ

        total += amount[0]
        reasons.add(amount[1])

    if not reasons:
        return None, ProposalReason.no_quantity

    reason = next(r for r in _REASON_PRECEDENCE if r in reasons)
    return total, reason


def _proposal(
    item: PantryItemOut, need: float | None, reason: ProposalReason, fraction: float, replaces: UUID | None = None
) -> PantryProposal:
    """The proposal for one item that has `fraction` of the recipe's `need` still to take."""
    if need is None:
        return PantryProposal(
            pantry_item_id=item.id,
            proposed_quantity=item.quantity,
            proposed_outcome=ProposedOutcome.some_left,
            reason=reason,
            replaces_reference_id=replaces,
        )

    assert item.quantity is not None  # a missing quantity gave `need=None`
    take = min(need * fraction, item.quantity)
    used = round(take, 3)

    if take < SMALL_AMOUNT_RATIO * item.quantity:
        return PantryProposal(
            pantry_item_id=item.id,
            used=used,
            proposed_quantity=item.quantity,
            proposed_outcome=ProposedOutcome.some_left,
            reason=ProposalReason.small_amount,
            replaces_reference_id=replaces,
        )

    left = round(item.quantity - take, 3)
    used_up = left <= _EPSILON
    return PantryProposal(
        pantry_item_id=item.id,
        used=used,
        proposed_quantity=0 if used_up else left,
        proposed_outcome=ProposedOutcome.used_up if used_up else ProposedOutcome.some_left,
        reason=reason,
        replaces_reference_id=replaces,
    )


def propose_for_food(lines: list[RecipeIngredient], items: list[PantryItemOut], scale: float) -> list[PantryProposal]:
    """One proposal per pantry item of a food, spilling the recipe's need over them in pantry order."""
    proposals: list[PantryProposal] = []
    remaining = 1.0  # the fraction of the recipe's need still to take

    for item in items:
        need, reason = amount_in_item(lines, item, scale)

        if remaining <= _EPSILON:
            # an earlier item covered the need: nothing left for this one, whether or not its units compare
            proposals.append(PantryProposal(pantry_item_id=item.id, proposed_outcome=ProposedOutcome.none))
            continue

        proposals.append(_proposal(item, need, reason, remaining))

        if need is not None and need > 0 and item.quantity:
            # a small amount still counts as taken, so a second item isn't charged for it
            remaining -= min(need * remaining, item.quantity) / need

    return proposals


def propose_substitute(
    lines: list[RecipeIngredient], item: PantryItemOut, scale: float, replaces: UUID | None
) -> PantryProposal:
    """The proposal for an item that stands in for a food: all the recipe's `lines` of it, no spill to other items."""
    need, reason = amount_in_item(lines, item, scale)
    return _proposal(item, need, reason, 1.0, replaces=replaces)
