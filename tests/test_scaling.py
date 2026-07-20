"""Tests for cooking-friendly rounding and fraction formatting used in scaling."""
import pytest

from app.services import units


def test_round_cooking_quarter_for_cups():
    assert units.round_cooking(0.83, "cup") == 0.75
    assert units.round_cooking(1.1, "tsp") == 1.0


def test_round_cooking_whole_for_grams():
    assert units.round_cooking(203.2, "g") == 205  # nearest 5 at >= 100
    assert units.round_cooking(12.4, "g") == 12


def test_round_cooking_count_to_quarter():
    assert units.round_cooking(2.9, None) == 3.0


def test_format_whole_number():
    assert units.format_quantity(3.0) == "3"


def test_format_half():
    assert units.format_quantity(0.5) == "1/2"


def test_format_mixed_number():
    assert units.format_quantity(1.5) == "1 1/2"
    assert units.format_quantity(2.25) == "2 1/4"


def test_format_third():
    assert units.format_quantity(1.0 / 3.0) == "1/3"


def test_format_rounds_up_to_whole():
    # 0.99 snaps up cleanly to a whole number rather than "0 8/8"
    assert units.format_quantity(0.99) == "1"


def test_scaling_ratio_example():
    # Scale 2 cups flour from 4 servings to 6 servings -> 3 cups.
    base_qty = 2.0
    scaled = base_qty * (6 / 4)
    assert units.round_cooking(scaled, "cup") == 3.0
    assert units.format_quantity(3.0) == "3"


def test_none_quantity_formats_empty():
    assert units.format_quantity(None) == ""
