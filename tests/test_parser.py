"""Tests for the ingredient parser."""
import pytest

from app.services.parser import normalize_unicode_fractions, parse_ingredient


def test_integer_quantity_with_unit():
    r = parse_ingredient("2 cups flour")
    assert r["parsed"] is True
    assert r["quantity"] == 2
    assert r["unit"] == "cup"
    assert r["name"] == "flour"
    assert r["quantity_max"] is None


def test_of_is_stripped_from_name():
    r = parse_ingredient("2 cups of flour")
    assert r["name"] == "flour"


def test_simple_fraction():
    r = parse_ingredient("1/2 tsp salt")
    assert r["quantity"] == pytest.approx(0.5)
    assert r["unit"] == "tsp"
    assert r["name"] == "salt"


def test_mixed_number():
    r = parse_ingredient("1 1/2 tablespoons olive oil")
    assert r["quantity"] == pytest.approx(1.5)
    assert r["unit"] == "tbsp"
    assert r["name"] == "olive oil"


def test_unicode_fraction():
    r = parse_ingredient("½ cup sugar")
    assert r["quantity"] == pytest.approx(0.5)
    assert r["unit"] == "cup"


def test_unicode_fraction_attached_to_whole():
    assert normalize_unicode_fractions("1½") == "1 1/2"
    r = parse_ingredient("1½ cups milk")
    assert r["quantity"] == pytest.approx(1.5)
    assert r["unit"] == "cup"


def test_decimal_quantity():
    r = parse_ingredient("0.5 kg beef")
    assert r["quantity"] == pytest.approx(0.5)
    assert r["unit"] == "kg"
    assert r["name"] == "beef"


def test_range_takes_low_and_high():
    r = parse_ingredient("1-2 cloves garlic")
    assert r["quantity"] == 1
    assert r["quantity_max"] == 2
    # "cloves" is not a normalized unit -> stays part of the name
    assert r["unit"] is None
    assert "garlic" in r["name"]


def test_range_with_word_to():
    r = parse_ingredient("2 to 3 cups water")
    assert r["quantity"] == 2
    assert r["quantity_max"] == 3
    assert r["unit"] == "cup"


def test_count_item_has_no_unit():
    r = parse_ingredient("3 eggs")
    assert r["parsed"] is True
    assert r["quantity"] == 3
    assert r["unit"] is None
    assert r["name"] == "eggs"


def test_unparsed_line_keeps_raw_text():
    r = parse_ingredient("salt and pepper to taste")
    assert r["parsed"] is False
    assert r["quantity"] is None
    assert r["raw_text"] == "salt and pepper to taste"


def test_grams_abbreviation():
    r = parse_ingredient("200 g dark chocolate")
    assert r["unit"] == "g"
    assert r["quantity"] == 200


def test_fluid_ounce_two_word_unit():
    r = parse_ingredient("8 fl oz milk")
    assert r["unit"] == "fl_oz"
    assert r["name"] == "milk"


def test_ounce_defaults_to_weight():
    r = parse_ingredient("4 oz butter")
    assert r["unit"] == "oz"


def test_leading_noise_removed():
    r = parse_ingredient("about 2 cups broth")
    assert r["quantity"] == 2
    assert r["unit"] == "cup"


def test_empty_line():
    r = parse_ingredient("   ")
    assert r["parsed"] is False
    assert r["raw_text"] == ""
