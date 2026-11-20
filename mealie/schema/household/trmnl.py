from enum import StrEnum

from mealie.schema._mealie import MealieModel


class TrmnlState(StrEnum):
    planned = "planned"
    nothing_planned = "nothing_planned"
    no_recipe = "no_recipe"


class TrmnlRecipe(MealieModel):
    name: str
    facts: str
    """Time, servings and last verdict, already in French and joined with " · "; empty when none is known."""
    image_url: str | None = None


class TrmnlToBuy(MealieModel):
    name: str
    quantity: str | None = None
    """What the recipe needs, e.g. "400 ml"; None when the recipe gives no quantity."""
    left: str | None = None
    """What the pantry still holds when it is not enough, e.g. "reste 50 ml"."""
    on_list: bool = False
    """Already on an unchecked shopping list item."""
    type: str = ""
    """The kind of food, e.g. "Légumes"; rows come sorted by it, in shopping-aisle order."""


class TrmnlAtHome(MealieModel):
    name: str
    use_soon: bool = False
    type: str = ""
    """The kind of food; the list comes sorted by it, so the screen can group it."""


class TrmnlUseSoon(MealieModel):
    name: str
    when: str
    """"2 j", "aujourd'hui", "dépassé" or "à vérifier"."""
    place: str = ""
    """Where it is kept, in French: "Frigo", "Congélateur", "Placard" or "Ailleurs"."""


class TrmnlPantryLine(MealieModel):
    name: str
    quantity: str
    """What there is, e.g. "500 g" or "2 paquets"."""


class TrmnlTypeGroup(MealieModel):
    """The foods of one kind in one place, e.g. the cupboard's "Féculents"."""

    name: str
    items: list[TrmnlPantryLine] = []


class TrmnlPlace(MealieModel):
    """One storage place of the pantry, for the screen shown when no meal is planned.

    Only items with a quantity are shown; staples kept without one are left out."""

    name: str
    """"Frigo", "Congélateur", "Placard" or "Ailleurs"."""
    count: int
    items: list[str] = []
    """Every name shown, soonest use-by first (kept for older templates)."""
    groups: list[TrmnlTypeGroup] = []
    """The same items by kind of food, in `food_type.TYPE_ORDER`; within a kind, soonest use-by first."""


class TrmnlTonightOut(MealieModel):
    """Everything the TRMNL "Ce soir" screen shows, display-ready: the template only reads it."""

    state: TrmnlState
    kicker: str
    generated_at: str
    recipe: TrmnlRecipe | None = None
    to_buy: list[TrmnlToBuy] = []
    to_buy_more: int = 0
    """Always 0 now: every row is sent and the template fits them (kept for older templates)."""
    at_home: list[TrmnlAtHome] = []
    """Ingredients at home, by kind of food; those whose pantry items have no quantity are left out."""
    ingredient_count: int = 0
    """Distinct foods judged: at home plus to buy."""
    to_check_count: int = 0
    """Ingredients the check can't judge; while above 0 the screen never says "Rien à acheter"."""
    use_soon: list[TrmnlUseSoon] = []
    """Pantry items to use up, worst first: when nothing is planned, and beside a meal without a recipe."""
    places: list[TrmnlPlace] = []
    """Only when nothing is planned: the pantry by place, fridge first, empty places left out."""
