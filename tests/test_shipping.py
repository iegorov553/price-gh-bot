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
    quote = estimate_shopfans_shipping("Arc'teryx Hoodie")
    assert quote.cost_usd == Decimal("18.99")
    assert quote.weight_kg == Decimal("0.70")


def test_estimate_shopfans_tee():
    """Test tee shirt shipping calculation."""
    quote = estimate_shopfans_shipping("Vintage Tee")
    assert quote.cost_usd == Decimal("16.99")
    assert quote.weight_kg == Decimal("0.20")


def test_estimate_shopfans_suitcase():
    """Test suitcase shipping calculation."""
    quote = estimate_shopfans_shipping("Large Suitcase")
    assert quote.cost_usd == Decimal("47.00")
    assert quote.weight_kg == Decimal("3.00")


def test_estimate_shopfans_default():
    """Test default weight when no pattern matches."""
    quote = estimate_shopfans_shipping("Unknown Item")
    assert quote.cost_usd == Decimal("18.99")
    assert quote.weight_kg == Decimal("0.60")


def test_estimate_shopfans_empty_string():
    """Test empty string uses default weight."""
    quote = estimate_shopfans_shipping("")
    assert quote.cost_usd == Decimal("18.99")
    assert quote.weight_kg == Decimal("0.60")


def test_estimate_shopfans_case_insensitive():
    """Test that matching is case insensitive."""
    quote1 = estimate_shopfans_shipping("HOODIE")
    assert quote1.cost_usd == Decimal("18.99")

    quote2 = estimate_shopfans_shipping("vintage tee shirt")
    assert quote2.cost_usd == Decimal("16.99")


def test_estimate_shopfans_sneakers():
    """Test sneakers shipping calculation."""
    quote = estimate_shopfans_shipping("Nike Sneakers")
    assert quote.cost_usd == Decimal("23.60")
    assert quote.weight_kg == Decimal("1.40")


def test_estimate_shopfans_boots():
    """Test boots shipping calculation."""
    quote = estimate_shopfans_shipping("Leather Boots")
    assert quote.cost_usd == Decimal("30.20")
    assert quote.weight_kg == Decimal("1.80")


def test_estimate_shopfans_light_items():
    """Test light items that use $3 handling fee."""
    quote1 = estimate_shopfans_shipping("Tie")
    assert quote1.cost_usd == Decimal("17.12")
    assert quote1.weight_kg == Decimal("0.08")

    quote2 = estimate_shopfans_shipping("Socks")
    assert quote2.cost_usd == Decimal("16.99")
    assert quote2.weight_kg == Decimal("0.05")


def test_calc_shipping_russia():
    """Test shipping calculation for Russia."""
    quote = calc_shipping("russia", Decimal("0.50"))
    assert quote.cost_usd == Decimal("20.00")
    assert quote.weight_kg == Decimal("0.50")


def test_calc_shipping_unsupported_country():
    """Test shipping calculation for unsupported country."""
    quote = calc_shipping("france", Decimal("0.50"))
    assert quote.cost_usd == Decimal("0")
    assert quote.weight_kg == Decimal("0.50")
    assert "not supported" in quote.description
