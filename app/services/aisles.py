"""Grocery-aisle categorization for shopping lists.

============================================================================
HOW TO CUSTOMIZE  (this is the file to edit for your own store layout)
============================================================================
* AISLE_ORDER      - the aisles, in the order they print on the shopping list.
* AISLE_KEYWORDS   - maps each aisle to a list of lowercase keywords. An
                     ingredient is filed under the FIRST aisle (in AISLE_ORDER)
                     whose keyword list matches the ingredient name.
* Matching is word-boundary based and case-insensitive, so "chicken" matches
  "chicken thighs" and "boneless chicken", but "cornflour" won't match "corn".
* Anything that matches nothing lands in the "other" aisle.

Add, remove, or reorder keywords freely. To make one aisle win ties over
another, place it earlier in AISLE_ORDER.
============================================================================
"""
from __future__ import annotations

import re

# Print/display order of aisles. "other" should stay last as the catch-all.
AISLE_ORDER: list[str] = [
    "produce",
    "meat",
    "seafood",
    "dairy",
    "bakery",
    "frozen",
    "pantry",
    "canned goods",
    "spices",
    "beverages",
    "other",
]

# Aisle -> keywords. Keep everything lowercase.
AISLE_KEYWORDS: dict[str, list[str]] = {
    "produce": [
        "apple", "banana", "orange", "lemon", "lime", "berry", "berries",
        "strawberry", "blueberry", "raspberry", "grape", "melon", "mango",
        "avocado", "tomato", "potato", "onion", "shallot", "garlic", "ginger",
        "carrot", "celery", "lettuce", "spinach", "kale", "cabbage", "broccoli",
        "cauliflower", "pepper", "chilli", "chili", "cucumber", "courgette",
        "zucchini", "aubergine", "eggplant", "mushroom", "leek", "corn",
        "peas", "bean sprout", "herbs", "parsley", "coriander", "cilantro",
        "basil", "mint", "rosemary", "thyme", "dill", "scallion", "spring onion",
        "green onion", "squash", "pumpkin", "beetroot", "radish", "asparagus",
        "sweet potato", "fennel", "watercress", "rocket", "arugula",
    ],
    "meat": [
        "chicken", "beef", "pork", "lamb", "veal", "turkey", "duck", "bacon",
        "sausage", "ham", "mince", "steak", "ground beef", "ground pork",
        "chorizo", "prosciutto", "pancetta", "salami", "ribs", "brisket",
    ],
    "seafood": [
        "fish", "salmon", "tuna", "cod", "haddock", "prawn", "shrimp", "crab",
        "lobster", "mussel", "clam", "oyster", "scallop", "squid", "calamari",
        "anchovy", "sardine", "mackerel", "trout", "sea bass",
    ],
    "dairy": [
        "milk", "cream", "butter", "cheese", "cheddar", "parmesan", "mozzarella",
        "yogurt", "yoghurt", "egg", "eggs", "creme fraiche", "sour cream",
        "buttermilk", "ricotta", "mascarpone", "feta", "ghee", "custard",
    ],
    "bakery": [
        "bread", "baguette", "roll", "bun", "bagel", "tortilla", "pitta",
        "pita", "croissant", "brioche", "naan", "ciabatta", "sourdough",
        "breadcrumb", "crumpet",
    ],
    "frozen": [
        "frozen", "ice cream", "ice-cream", "sorbet", "frozen peas",
        "frozen berries", "puff pastry", "shortcrust pastry", "filo", "phyllo",
    ],
    "pantry": [
        "flour", "sugar", "brown sugar", "icing sugar", "powdered sugar",
        "baking powder", "baking soda", "bicarbonate", "yeast", "cornflour",
        "cornstarch", "cocoa", "chocolate", "oats", "rice", "pasta", "noodle",
        "spaghetti", "lentil", "chickpea", "quinoa", "couscous", "oil",
        "olive oil", "vegetable oil", "vinegar", "honey", "syrup", "maple",
        "vanilla", "peanut butter", "jam", "marmalade", "nut", "almond",
        "walnut", "cashew", "pecan", "raisin", "sultana", "date", "seed",
        "sesame", "soy sauce", "fish sauce", "worcestershire", "mustard",
        "ketchup", "mayonnaise", "mayo", "gelatin", "gelatine", "cornmeal",
        "polenta", "breadcrumbs", "stock cube", "bouillon", "tahini", "miso",
    ],
    "canned goods": [
        "canned", "can of", "tinned", "tin of", "chopped tomatoes",
        "crushed tomatoes", "tomato paste", "tomato puree", "passata",
        "coconut milk", "coconut cream", "baked beans", "kidney beans",
        "black beans", "cannellini", "sweetcorn", "tuna in", "stock", "broth",
    ],
    "spices": [
        "salt", "black pepper", "peppercorn", "paprika", "cumin", "turmeric",
        "cinnamon", "nutmeg", "cardamom", "clove", "cayenne", "chilli powder",
        "chili powder", "curry powder", "garam masala", "oregano", "bay leaf",
        "bay leaves", "allspice", "coriander seed", "cumin seed", "saffron",
        "star anise", "fenugreek", "mustard seed", "chilli flakes",
        "red pepper flakes", "seasoning", "spice",
    ],
    "beverages": [
        "water", "juice", "wine", "beer", "cider", "coffee", "tea", "cola",
        "soda", "lemonade", "sparkling water", "tonic", "vodka", "rum",
        "brandy", "sherry", "vermouth", "whisky", "whiskey",
    ],
    # "other" has no keywords; it is the fallback bucket.
    "other": [],
}


def _compile(keywords: list[str]) -> list[re.Pattern]:
    # Word-boundary match with an optional plural suffix, so "tomato" matches
    # "tomatoes" but "corn" still does NOT match "cornflour".
    return [
        re.compile(r"\b" + re.escape(kw) + r"(?:e?s)?\b", re.IGNORECASE)
        for kw in keywords
    ]


# Precompile keyword patterns once, keyed by aisle.
_COMPILED: dict[str, list[re.Pattern]] = {
    aisle: _compile(AISLE_KEYWORDS.get(aisle, [])) for aisle in AISLE_ORDER
}


def categorize(name: str | None) -> str:
    """Return the aisle for an ingredient name (falls back to 'other')."""
    if not name:
        return "other"
    text = name.lower()
    for aisle in AISLE_ORDER:
        for pat in _COMPILED[aisle]:
            if pat.search(text):
                return aisle
    return "other"
