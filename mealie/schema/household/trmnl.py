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


class TrmnlAtHome(MealieModel):
    name: str
    use_soon: bool = False


class TrmnlUseSoon(MealieModel):
    name: str
    when: str
    """"2 j", "aujourd'hui", "dépassé" or "à vérifier"."""
    place: str = ""
    """Where it is kept, in French: "Frigo", "Congélateur", "Placard" or "Ailleurs"."""


class TrmnlPlace(MealieModel):
    """One storage place of the pantry, for the screen shown when no meal is planned."""

    name: str
    """"Frigo", "Congélateur", "Placard" or "Ailleurs"."""
    count: int
    items: list[str] = []
    """The first names, soonest use-by first; `count` says how many there are in all."""


class TrmnlTonightOut(MealieModel):
    """Everything the TRMNL "Ce soir" screen shows, display-ready: the template only reads it."""

    state: TrmnlState
    kicker: str
    generated_at: str
    recipe: TrmnlRecipe | None = None
    to_buy: list[TrmnlToBuy] = []
    to_buy_more: int = 0
    """Rows left out of `to_buy` to fit the screen."""
    at_home: list[TrmnlAtHome] = []
    ingredient_count: int = 0
    """Distinct foods judged: at home plus to buy."""
    to_check_count: int = 0
    """Ingredients the check can't judge; while above 0 the screen never says "Rien à acheter"."""
    use_soon: list[TrmnlUseSoon] = []
    places: list[TrmnlPlace] = []
    """Only when nothing is planned: the pantry by place, fridge first, empty places left out."""
