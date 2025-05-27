import pytest
from decimal import Decimal
from shipping_estimator import estimate_shopfans_shipping


def test_estimate_shopfans_hoodie():
    """Test hoodie shipping calculation."""
    assert estimate_shopfans_shipping("Arc'teryx Hoodie") == Decimal("18.99")


def test_estimate_shopfans_tee():
    """Test tee shirt shipping calculation."""
    assert estimate_shopfans_shipping("Vintage Tee") == Decimal("16.99")


def test_estimate_shopfans_suitcase():
    """Test suitcase shipping calculation."""
    assert estimate_shopfans_shipping("Large Suitcase") == Decimal("47.00")


def test_estimate_shopfans_default():
    """Test default weight when no pattern matches."""
    assert estimate_shopfans_shipping("Unknown Item") == Decimal("18.99")


def test_estimate_shopfans_empty_string():
    """Test empty string uses default weight."""
    assert estimate_shopfans_shipping("") == Decimal("18.99")


def test_estimate_shopfans_case_insensitive():
    """Test that matching is case insensitive."""
    assert estimate_shopfans_shipping("HOODIE") == Decimal("18.99")
    assert estimate_shopfans_shipping("vintage tee shirt") == Decimal("16.99")


def test_estimate_shopfans_sneakers():
    """Test sneakers shipping calculation."""
    assert estimate_shopfans_shipping("Nike Sneakers") == Decimal("23.60")


def test_estimate_shopfans_boots():
    """Test boots shipping calculation.""" 
    assert estimate_shopfans_shipping("Leather Boots") == Decimal("30.20")


def test_estimate_shopfans_light_items():
    """Test light items that use $3 handling fee."""
    assert estimate_shopfans_shipping("Tie") == Decimal("17.12")
    assert estimate_shopfans_shipping("Socks") == Decimal("16.99")