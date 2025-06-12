"""Tests for Shopfans shipping cost estimation service.

This module contains tests for the shipping service that:
- Estimates shipping costs and weights based on item categorization
- Applies Shopfans Lite pricing formula with handling fees
- Handles pattern matching for different product types (clothing, shoes, etc.)
- Provides fallback calculations for unrecognized items
"""

from decimal import Decimal

from app.services.shipping import calc_shipping, estimate_shopfans_shipping


def test_estimate_shopfans_hoodie():
    """Test hoodie shipping calculation."""
    # Using $150 order total (Europe route: 30.86$/kg)
    quote = estimate_shopfans_shipping("Arc'teryx Hoodie", Decimal("150"))
    # 0.70kg * 30.86 = 21.60 + 3 handling = 24.60
    assert quote.cost_usd == Decimal("24.60")
    assert quote.weight_kg == Decimal("0.70")


def test_estimate_shopfans_tee():
    """Test tee shirt shipping calculation."""
    quote = estimate_shopfans_shipping("Vintage Tee", Decimal("100"))
    # 0.20kg * 30.86 = 6.17, but min cost is 13.99 + 3 handling = 16.99
    assert quote.cost_usd == Decimal("16.99")
    assert quote.weight_kg == Decimal("0.20")


def test_estimate_shopfans_suitcase():
    """Test suitcase shipping calculation."""
    quote = estimate_shopfans_shipping("Large Suitcase", Decimal("500"))
    # 3.00kg * 35.27 = 105.81 + 5 handling = 110.81 (Turkey route for $500)
    assert quote.cost_usd == Decimal("110.81")
    assert quote.weight_kg == Decimal("3.00")


def test_estimate_shopfans_default():
    """Test default weight when no pattern matches."""
    quote = estimate_shopfans_shipping("Unknown Item", Decimal("150"))
    # 0.60kg * 30.86 = 18.52 + 3 handling = 21.52
    assert quote.cost_usd == Decimal("21.52")
    assert quote.weight_kg == Decimal("0.60")


def test_estimate_shopfans_empty_string():
    """Test empty string uses default weight."""
    quote = estimate_shopfans_shipping("", Decimal("150"))
    # 0.60kg * 30.86 = 18.52 + 3 handling = 21.52
    assert quote.cost_usd == Decimal("21.52")
    assert quote.weight_kg == Decimal("0.60")


def test_estimate_shopfans_case_insensitive():
    """Test that matching is case insensitive."""
    quote1 = estimate_shopfans_shipping("HOODIE", Decimal("150"))
    # 0.70kg * 30.86 = 21.60 + 3 handling = 24.60
    assert quote1.cost_usd == Decimal("24.60")

    quote2 = estimate_shopfans_shipping("vintage tee shirt", Decimal("100"))
    assert quote2.cost_usd == Decimal("16.99")


def test_estimate_shopfans_sneakers():
    """Test sneakers shipping calculation."""
    quote = estimate_shopfans_shipping("Nike Sneakers", Decimal("150"))
    # 1.40kg * 30.86 = 43.20 + 5 handling = 48.20 (heavy item > 1.36kg)
    assert quote.cost_usd == Decimal("48.20")
    assert quote.weight_kg == Decimal("1.40")


def test_estimate_shopfans_boots():
    """Test boots shipping calculation."""
    quote = estimate_shopfans_shipping("Leather Boots", Decimal("200"))
    # 1.80kg * 35.27 = 63.49 + 5 handling = 68.49 (Turkey route for $200)
    assert quote.cost_usd == Decimal("68.49")
    assert quote.weight_kg == Decimal("1.80")


def test_estimate_shopfans_light_items():
    """Test light items that use $3 handling fee."""
    quote1 = estimate_shopfans_shipping("Tie", Decimal("100"))
    # 0.08kg * 30.86 = 2.47, but min cost is 13.99 + 3 handling = 16.99
    assert quote1.cost_usd == Decimal("16.99")
    assert quote1.weight_kg == Decimal("0.08")

    quote2 = estimate_shopfans_shipping("Socks", Decimal("100"))
    assert quote2.cost_usd == Decimal("16.99")
    assert quote2.weight_kg == Decimal("0.05")


def test_calc_shipping_russia():
    """Test shipping calculation for Russia."""
    quote = calc_shipping("russia", Decimal("0.50"), Decimal("150"))
    # 0.50kg * 30.86 = 15.43 + 3 handling = 18.43
    assert quote.cost_usd == Decimal("18.43")
    assert quote.weight_kg == Decimal("0.50")


def test_calc_shipping_unsupported_country():
    """Test shipping calculation for unsupported country."""
    quote = calc_shipping("france", Decimal("0.50"), Decimal("150"))
    assert quote.cost_usd == Decimal("0")
    assert quote.weight_kg == Decimal("0.50")
    assert "not supported" in quote.description
