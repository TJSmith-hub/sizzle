"""Tests for the ingredient grouping heuristic."""
from app.services.grouping import group_ingredients, is_header


def test_colon_line_is_header():
    assert is_header("For the sauce:") is True


def test_for_the_prefix_is_header():
    assert is_header("For the dough") is True


def test_to_serve_is_header():
    assert is_header("To serve") is True


def test_all_caps_short_is_header():
    assert is_header("DOUGH") is True


def test_line_with_digit_is_not_header():
    assert is_header("2 cups flour") is False


def test_plain_ingredient_not_header():
    # The conservative default must NOT treat a bare ingredient as a header.
    assert is_header("salt") is False
    assert is_header("olive oil") is False


def test_grouping_splits_on_headers():
    lines = [
        "For the dough:",
        "2 cups flour",
        "1 tsp salt",
        "For the filling:",
        "3 apples",
        "1/2 cup sugar",
    ]
    groups = group_ingredients(lines)
    assert len(groups) == 2
    assert groups[0]["title"] == "For the dough"
    assert groups[0]["ingredients"] == ["2 cups flour", "1 tsp salt"]
    assert groups[1]["title"] == "For the filling"
    assert groups[1]["ingredients"] == ["3 apples", "1/2 cup sugar"]


def test_ingredients_before_first_header_go_to_default_group():
    lines = ["2 cups flour", "For the topping:", "1 tbsp sugar"]
    groups = group_ingredients(lines)
    assert groups[0]["title"] is None
    assert groups[0]["ingredients"] == ["2 cups flour"]
    assert groups[1]["title"] == "For the topping"


def test_no_headers_returns_single_default_group():
    lines = ["2 cups flour", "1 tsp salt", "3 eggs"]
    groups = group_ingredients(lines)
    assert len(groups) == 1
    assert groups[0]["title"] is None
    assert len(groups[0]["ingredients"]) == 3


def test_blank_lines_ignored():
    groups = group_ingredients(["", "  ", "2 cups flour"])
    assert len(groups) == 1
    assert groups[0]["ingredients"] == ["2 cups flour"]
