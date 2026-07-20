"""Tests for grocery-aisle categorization."""
from app.services.aisles import categorize


def test_meat():
    assert categorize("boneless chicken thighs") == "meat"
    assert categorize("beef mince") == "meat"


def test_dairy():
    assert categorize("whole milk") == "dairy"
    assert categorize("cheddar cheese") == "dairy"
    assert categorize("2 eggs") == "dairy"


def test_produce():
    assert categorize("ripe tomatoes") == "produce"
    assert categorize("garlic cloves") == "produce"


def test_pantry():
    assert categorize("all-purpose flour") == "pantry"
    assert categorize("olive oil") == "pantry"


def test_spices():
    assert categorize("ground cumin") == "spices"
    assert categorize("salt") == "spices"


def test_seafood():
    assert categorize("fresh salmon fillet") == "seafood"


def test_word_boundary_prevents_false_match():
    # "corn" should not match inside "cornflour" (which is pantry).
    assert categorize("cornflour") == "pantry"


def test_unknown_goes_to_other():
    assert categorize("dragon fruit powder") == "other"
    assert categorize("") == "other"
    assert categorize(None) == "other"
