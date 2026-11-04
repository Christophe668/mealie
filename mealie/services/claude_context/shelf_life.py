"""How long a pantry item typically keeps, so the pantry can say what to use first or check.

These are rough household guidelines, not food-safety rules: the UI and Claude present them as estimates.
A keeping time set on the food (its `shelf_life_days_opened` / `shelf_life_days_unopened` extras) always
wins over the built-in table; an explicit use-by date on the item wins over both (callers handle that).
"""

import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from typing import Literal

ShelfLifeSource = Literal["food", "typical"]

FOOD_EXTRA_OPENED = "shelf_life_days_opened"
FOOD_EXTRA_UNOPENED = "shelf_life_days_unopened"

FREEZER_DAYS = (90, 180)
"""Anything kept in the freezer: about three months once opened, six sealed."""

THAWED_DAYS = (1, 1)
"""Something sold frozen but not kept in the freezer."""

LEFTOVER_DAYS = (3, 3)
"""Cooked leftovers in the fridge."""

_FROZEN_WORDS = ("surgele", "frozen", "congele")


@dataclass(frozen=True)
class ShelfLife:
    opened_days: int | None
    unopened_days: int | None
    source: ShelfLifeSource


# (keywords, days once opened, days unopened). Keywords are matched as whole words, accents and case
# ignored, with an optional plural ending; the longest matching keyword wins ("oignon frit" over "oignon").
# Fresh produce has no "opened" state, so both numbers are the same.
_TABLE: tuple[tuple[tuple[str, ...], int, int], ...] = (
    # Bread and bakery
    (("baguette", "ficelle"), 2, 2),
    (("pain", "bread"), 3, 3),
    (("pain de mie", "sliced bread", "pain burger", "burger bun", "pain hot dog", "hot dog bun"), 5, 7),
    (("brioche",), 4, 5),
    (("croissant", "pain au chocolat", "viennoiserie"), 2, 2),
    (("tortilla", "wrap", "pita"), 5, 21),
    # Dairy and eggs
    (("lait", "milk"), 4, 7),
    (("lait uht", "uht milk", "lait de coco", "coconut milk"), 4, 180),
    (("creme", "cream", "creme fraiche", "sour cream"), 5, 14),
    (("yaourt", "yogourt", "yogurt", "yoghurt", "skyr", "fromage blanc"), 3, 14),
    (("beurre", "butter"), 30, 60),
    (("oeuf", "egg"), 28, 28),
    (("fromage", "cheese"), 14, 30),
    (("fromage rape", "grated cheese", "shredded cheese"), 5, 21),
    (("gruyere", "comte", "emmental", "cheddar", "gouda", "beaufort", "manchego"), 21, 60),
    (("parmesan", "parmigiano", "grana padano", "pecorino"), 30, 120),
    (("mozzarella", "burrata", "ricotta", "mascarpone"), 3, 14),
    (("brie", "camembert", "chevre", "goat cheese", "roquefort", "bleu", "feta"), 7, 21),
    # Meat and fish
    (("viande hachee", "hache", "minced meat", "ground beef"), 1, 2),
    (("poulet", "chicken", "dinde", "turkey", "canard", "duck"), 2, 3),
    (("boeuf", "beef", "steak", "porc", "pork", "agneau", "lamb", "veau", "veal"), 3, 4),
    (("jambon", "ham"), 4, 14),
    (("lardon", "bacon", "pancetta"), 5, 21),
    (("saucisse", "sausage", "chipolata", "merguez"), 3, 7),
    (("knacki", "saucisse de strasbourg", "frankfurter", "hot dog"), 3, 21),
    (("chorizo", "salami", "saucisson", "coppa"), 21, 60),
    (("poisson", "fish", "saumon", "salmon", "cabillaud", "cod", "crevette", "shrimp", "prawn"), 1, 2),
    (("saumon fume", "smoked salmon"), 3, 14),
    (("tofu",), 4, 30),
    # Vegetables and herbs
    (("salade", "laitue", "lettuce", "roquette", "rocket", "arugula", "epinard", "spinach", "mache"), 3, 5),
    (
        ("persil", "parsley", "coriandre", "cilantro", "basilic", "basil", "ciboulette", "chives", "menthe", "mint"),
        4,
        5,
    ),
    (("champignon", "mushroom"), 3, 5),
    (
        ("tomate", "tomato", "concombre", "cucumber", "courgette", "zucchini", "poivron", "bell pepper", "aubergine"),
        6,
        7,
    ),
    (("brocoli", "broccoli", "chou fleur", "cauliflower", "haricot vert", "green bean", "asperge", "asparagus"), 4, 5),
    (("carotte", "carrot", "chou", "cabbage", "celeri", "celery", "poireau", "leek", "betterave", "beetroot"), 14, 14),
    (("oignon", "onion", "echalote", "shallot"), 30, 30),
    (("ail", "garlic"), 7, 60),
    (("pomme de terre", "potato", "patate"), 30, 30),
    (("gingembre", "ginger"), 14, 21),
    (("avocat", "avocado"), 2, 5),
    # Fruit
    (("banane", "banana"), 5, 5),
    (("pomme", "apple", "poire", "pear"), 21, 21),
    (("orange", "clementine", "mandarine", "citron", "lemon", "lime"), 14, 14),
    (("fraise", "strawberry", "framboise", "raspberry", "myrtille", "blueberry", "mure", "blackberry"), 2, 3),
    (("raisin", "grape", "peche", "peach", "abricot", "apricot", "prune", "plum", "kiwi", "mangue", "mango"), 5, 7),
    # Sauces, condiments and jars
    (("ketchup",), 180, 365),
    (("mayonnaise", "mayo"), 60, 180),
    (("moutarde", "mustard"), 90, 365),
    (("cornichon", "pickle", "gherkin", "capre", "caper", "olive"), 60, 365),
    (("pesto",), 5, 180),
    (("sauce tomate", "tomato sauce", "passata", "coulis", "concentre de tomate", "tomato paste"), 5, 365),
    (("sauce soja", "soy sauce", "nuoc mam", "fish sauce", "vinaigre", "vinegar"), 365, 730),
    (("confiture", "jam", "pate a tartiner", "nutella"), 60, 365),
    (("miel", "honey"), 730, 730),
    (("huile", "oil", "huile d olive", "olive oil"), 180, 540),
    (("bouillon", "stock cube"), 365, 730),
    # Dry goods
    (("sucre", "sugar", "sel", "salt"), 730, 730),
    (("farine", "flour", "maizena", "cornstarch", "fecule", "levure", "yeast", "chapelure", "breadcrumb"), 180, 365),
    (("pate", "pates", "pasta", "spaghetti", "penne", "tagliatelle", "nouille", "noodle", "riz", "rice"), 365, 730),
    (("lentille", "lentil", "pois chiche", "chickpea", "haricot sec", "semoule", "couscous", "quinoa"), 365, 730),
    (("conserve", "canned", "en boite"), 3, 730),
    (("epice", "spice", "paprika", "cumin", "curry", "poivre", "cannelle", "cinnamon", "herbes de provence"), 365, 730),
    (("noix", "nut", "cajou", "cashew", "pistache", "pistachio", "amande", "almond", "noisette", "hazelnut"), 60, 180),
    (("oignon frit", "fried onion", "crispy onion"), 60, 180),
    (("chocolat", "chocolate", "cacao", "cocoa"), 180, 365),
    (("cereale", "cereal", "muesli", "granola", "flocon d avoine", "oat"), 60, 365),
    (("biscuit", "cookie", "chips", "crackers"), 14, 180),
)


def _normalize(text: str) -> str:
    """Lowercase, accents removed, anything that is not a letter or digit turned into a single space."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    words = [re.escape(word) + r"(?:s|x|es)?" for word in _normalize(keyword).split()]
    return re.compile(r"\b" + r" ".join(words) + r"\b")


@cache
def _compiled_table() -> list[tuple[int, re.Pattern[str], int, int]]:
    """Every keyword with its length (to rank matches) and its days, longest keyword first."""
    rows = [
        (len(_normalize(keyword)), _keyword_pattern(keyword), opened, unopened)
        for keywords, opened, unopened in _TABLE
        for keyword in keywords
    ]
    return sorted(rows, key=lambda row: row[0], reverse=True)


def typical_days(text: str) -> tuple[int, int] | None:
    """(days once opened, days unopened) for the longest table keyword found in `text`, else None."""
    normalized = _normalize(text)
    if not normalized:
        return None
    for _, pattern, opened, unopened in _compiled_table():
        if pattern.search(normalized):
            return opened, unopened
    return None


def _is_frozen(text: str) -> bool:
    normalized = _normalize(text)
    return any(re.search(rf"\b{word}(?:e|s|es)?\b", normalized) for word in _FROZEN_WORDS)


def _extra_days(extras: dict | None, key: str) -> int | None:
    """A whole number of days from the food's extras; extras are stored as strings, so numeric strings count."""
    value = (extras or {}).get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value > 0 else None
    if isinstance(value, str):
        try:
            days = int(value.strip())
        except ValueError:
            return None
        return days if days > 0 else None
    return None


def estimate_shelf_life(
    *,
    name: str,
    location: str,
    source: str,
    note: str | None = None,
    food_name: str | None = None,
    food_extras: dict | None = None,
) -> ShelfLife | None:
    """
    How long the item keeps, in this order:

    1. kept in the freezer: about three months opened, six sealed;
    2. a leftover (cooked, whatever the food): three days;
    3. the food's own keeping times (its extras), each missing one filled from the table below;
    4. sold frozen (the name or note says so) but kept elsewhere: a day;
    5. the built-in table, on the item's name and its food's name, then on its note.

    None when nothing applies; the item then simply has no estimate.
    """
    if location == "freezer":
        return ShelfLife(*FREEZER_DAYS, source="typical")
    if source == "leftover":
        return ShelfLife(*LEFTOVER_DAYS, source="typical")

    names = " ".join(part for part in (name, food_name) if part)
    typical = typical_days(names) or typical_days(note or "")

    opened = _extra_days(food_extras, FOOD_EXTRA_OPENED)
    unopened = _extra_days(food_extras, FOOD_EXTRA_UNOPENED)
    if opened is not None or unopened is not None:
        return ShelfLife(
            opened_days=opened if opened is not None else (typical[0] if typical else None),
            unopened_days=unopened if unopened is not None else (typical[1] if typical else None),
            source="food",
        )

    if _is_frozen(f"{names} {note or ''}"):
        return ShelfLife(*THAWED_DAYS, source="typical")
    if typical:
        return ShelfLife(*typical, source="typical")
    return None
