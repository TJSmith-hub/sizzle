"""Tests for the persistent shopping list: display view + adding a recipe."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud import add_recipe_to_shopping_list, add_shopping_item
from app.database import Base
from app.models import Ingredient, IngredientGroup, Recipe, ShoppingListItem
from app.services.shopping_list import build_shopping_view, normalize_name


def _item(**kwargs):
    defaults = {
        "id": 1, "name": "Onion", "quantity": None, "quantity_max": None,
        "unit": None, "note": None, "source": None, "checked": False,
    }
    defaults.update(kwargs)
    return ShoppingListItem(**defaults)


def test_build_shopping_view_buckets_by_aisle():
    items = [
        _item(id=1, name="onion"),
        _item(id=2, name="chicken breast"),
    ]
    aisles = build_shopping_view(items, "metric")
    aisle_names = [a["aisle"] for a in aisles]
    assert "produce" in aisle_names
    assert "meat" in aisle_names


def test_build_shopping_view_converts_quantity_to_system():
    items = [_item(id=1, name="milk", quantity=500, unit="ml")]
    aisles = build_shopping_view(items, "imperial")
    item = aisles[0]["items"][0]
    assert item.unit in ("cup", "fl_oz")
    assert item.display_quantity() != ""


def test_build_shopping_view_keeps_count_items_unconverted():
    items = [_item(id=1, name="eggs", quantity=6, unit=None)]
    aisles = build_shopping_view(items, "imperial")
    item = aisles[0]["items"][0]
    assert item.unit is None
    assert item.display_quantity() == "6"


def test_build_shopping_view_range_endpoints_share_a_unit():
    # 800 ml – 1200 ml straddles the ml->l promotion: both ends must be
    # expressed in the SAME unit, not "800–1 ml" (max misrounded in the low
    # end's unit).
    items = [_item(id=1, name="milk", quantity=800, quantity_max=1200, unit="ml")]
    aisles = build_shopping_view(items, "metric")
    item = aisles[0]["items"][0]
    assert item.unit == "l"
    assert item.quantity == 0.8
    assert item.quantity_max == 1.2


def test_build_shopping_view_count_range_unconverted():
    items = [_item(id=1, name="garlic", quantity=1, quantity_max=2, unit=None)]
    aisles = build_shopping_view(items, "metric")
    item = aisles[0]["items"][0]
    assert item.unit is None
    assert item.display_quantity() == "1–2"


def test_build_shopping_view_no_quantity_renders_blank():
    items = [_item(id=1, name="salt", quantity=None)]
    aisles = build_shopping_view(items, "metric")
    item = aisles[0]["items"][0]
    assert item.display_quantity() == ""


def test_build_shopping_view_sorts_unchecked_before_checked():
    items = [
        _item(id=1, name="zucchini", checked=True),
        _item(id=2, name="apple", checked=False),
    ]
    aisles = build_shopping_view(items, "metric")
    names = [i.name for i in aisles[0]["items"]]
    assert names == ["apple", "zucchini"]


def test_build_shopping_view_empty_aisles_omitted():
    aisles = build_shopping_view([], "metric")
    assert aisles == []


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_add_recipe_to_shopping_list_creates_rows_per_ingredient():
    db = _make_session()
    recipe = Recipe(title="Test Soup")
    group = IngredientGroup(title=None, position=0)
    group.ingredients.append(
        Ingredient(raw_text="1 onion, finely chopped", quantity=1, unit=None, name="onion",
                   note="finely chopped", parsed=True, position=0)
    )
    group.ingredients.append(
        Ingredient(raw_text="salt to taste", quantity=None, name="salt to taste",
                   parsed=False, position=1)
    )
    recipe.groups.append(group)
    db.add(recipe)
    db.commit()

    added = add_recipe_to_shopping_list(db, recipe)

    assert added == 2
    rows = db.query(ShoppingListItem).order_by(ShoppingListItem.id).all()
    assert [r.name for r in rows] == ["onion", "salt to taste"]
    assert rows[0].quantity == 1
    assert rows[0].source == "Test Soup"
    assert rows[0].note is None  # prep notes aren't carried onto the shopping list
    assert rows[1].quantity is None  # unparsed ingredient carries no quantity


def test_add_recipe_to_shopping_list_skips_blank_names():
    db = _make_session()
    recipe = Recipe(title="Empty")
    group = IngredientGroup(title=None, position=0)
    group.ingredients.append(
        Ingredient(raw_text="   ", quantity=None, name=None, parsed=False, position=0)
    )
    recipe.groups.append(group)
    db.add(recipe)
    db.commit()

    added = add_recipe_to_shopping_list(db, recipe)
    assert added == 0


def test_normalize_name_strips_prep_words_and_singularizes():
    assert normalize_name("Large Onions, diced") == "onion"
    assert normalize_name("onion") == "onion"
    assert normalize_name("Chopped Tomatoes (400g)") == "tomato"
    assert normalize_name(None) == ""


def test_add_shopping_item_merges_matching_unchecked_rows():
    db = _make_session()
    add_shopping_item(db, name="onion", quantity=1, unit=None, source="Recipe A")
    add_shopping_item(db, name="chopped onions", quantity=2, unit=None, source="Recipe B")

    rows = db.query(ShoppingListItem).all()
    assert len(rows) == 1
    assert rows[0].quantity == 3
    assert rows[0].source == "Recipe A, Recipe B"


def test_add_shopping_item_converts_units_before_summing():
    db = _make_session()
    add_shopping_item(db, name="milk", quantity=1, unit="cup")
    add_shopping_item(db, name="milk", quantity=100, unit="ml")

    rows = db.query(ShoppingListItem).all()
    assert len(rows) == 1
    assert rows[0].unit == "cup"
    assert rows[0].quantity > 1  # 1 cup + ~0.42 cup


def test_add_shopping_item_does_not_merge_across_measurement_types():
    db = _make_session()
    add_shopping_item(db, name="flour", quantity=200, unit="g")
    add_shopping_item(db, name="flour", quantity=2, unit="cup")

    rows = db.query(ShoppingListItem).all()
    assert len(rows) == 2  # weight vs volume -- never guessed


def test_add_shopping_item_does_not_merge_into_checked_row():
    db = _make_session()
    existing = add_shopping_item(db, name="onion", quantity=1, unit=None)
    existing.checked = True
    db.commit()

    add_shopping_item(db, name="onion", quantity=1, unit=None)

    rows = db.query(ShoppingListItem).all()
    assert len(rows) == 2


def test_add_shopping_item_without_quantity_never_merges():
    db = _make_session()
    add_shopping_item(db, name="salt to taste", quantity=None)
    add_shopping_item(db, name="salt to taste", quantity=None)

    rows = db.query(ShoppingListItem).all()
    assert len(rows) == 2


def test_add_recipe_to_shopping_list_combines_across_recipes():
    db = _make_session()

    def _recipe(title, ing_name, qty):
        recipe = Recipe(title=title)
        group = IngredientGroup(title=None, position=0)
        group.ingredients.append(
            Ingredient(raw_text=f"{qty} {ing_name}", quantity=qty, unit=None,
                       name=ing_name, parsed=True, position=0)
        )
        recipe.groups.append(group)
        db.add(recipe)
        db.commit()
        return recipe

    r1 = _recipe("Soup", "onion", 1)
    r2 = _recipe("Stew", "onions", 2)

    add_recipe_to_shopping_list(db, r1)
    add_recipe_to_shopping_list(db, r2)

    rows = db.query(ShoppingListItem).all()
    assert len(rows) == 1
    assert rows[0].quantity == 3
    assert rows[0].source == "Soup, Stew"
