"""Tests for unit conversion, system selection, and temperature conversion."""
import pytest

from app.services import units


def test_convert_within_volume():
    # 1 cup ~= 236.588 ml
    assert units.convert(1, "cup", "ml") == pytest.approx(236.588, rel=1e-4)
    assert units.convert(1000, "ml", "l") == pytest.approx(1.0)


def test_convert_within_weight():
    assert units.convert(1, "kg", "g") == pytest.approx(1000.0)
    assert units.convert(16, "oz", "lb") == pytest.approx(1.0, rel=1e-3)


def test_convert_incompatible_types_returns_none():
    # volume <-> weight must never be attempted
    assert units.convert(1, "cup", "g") is None
    assert units.convert(1, "oz", "ml") is None


def test_convert_count_incompatible_with_measured():
    assert units.convert(1, None, "g") is None


def test_same_unit_is_identity():
    assert units.convert(5, "g", "g") == 5
    assert units.convert(3, None, None) == 3


def test_to_system_metric_promotes_to_litres():
    qty, unit = units.to_system(1500, "ml", "metric")
    assert unit == "l"
    assert qty == pytest.approx(1.5)


def test_to_system_metric_weight_promotes_to_kg():
    qty, unit = units.to_system(1200, "g", "metric")
    assert unit == "kg"
    assert qty == pytest.approx(1.2)


def test_to_system_imperial_volume_picks_cup():
    qty, unit = units.to_system(500, "ml", "imperial")
    assert unit in ("cup", "fl_oz")  # ~2.1 cups
    assert qty > 0


@pytest.mark.parametrize("unit", ["tsp", "tbsp", "cup"])
def test_to_system_metric_keeps_spoon_and_cup_units(unit):
    # Spoon/cup measures read naturally in metric recipes -- don't force ml/l.
    qty, out_unit = units.to_system(2, unit, "metric")
    assert out_unit == unit
    assert qty == 2


def test_to_system_metric_still_converts_fl_oz():
    qty, unit = units.to_system(8, "fl_oz", "metric")
    assert unit in ("ml", "l")


def test_to_system_imperial_still_converts_ml_to_spoon_units():
    qty, unit = units.to_system(4.92892, "ml", "imperial")
    assert unit == "tsp"
    assert qty == pytest.approx(1.0, rel=1e-3)


def test_to_system_count_unchanged():
    assert units.to_system(3, None, "metric") == (3, None)


def test_measurement_type():
    assert units.measurement_type("cup") == units.VOLUME
    assert units.measurement_type("g") == units.WEIGHT
    assert units.measurement_type(None) == units.COUNT


def test_temperature_f_to_c():
    out = units.convert_temperatures("Bake at 350F until golden", "metric")
    assert "175°C" in out or "180°C" in out


def test_temperature_c_to_f():
    out = units.convert_temperatures("Preheat oven to 180°C", "imperial")
    assert "°F" in out


def test_temperature_already_target_untouched():
    out = units.convert_temperatures("Bake at 180C", "metric")
    assert "180C" in out  # unchanged


def test_normalize_unit_synonyms():
    assert units.normalize_unit("tablespoons") == "tbsp"
    assert units.normalize_unit("g") == "g"
    assert units.normalize_unit("nonsense") is None
