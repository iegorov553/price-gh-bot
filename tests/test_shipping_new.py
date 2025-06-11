"""Tests for updated Shopfans shipping cost estimation service with tiered pricing.

This module contains tests for the shipping service that:
- Uses tiered pricing based on order total (Europe/Turkey/Kazakhstan routes)
- Estimates shipping costs and weights based on item categorization
- Applies new handling fee thresholds (1.36kg instead of 0.45kg)
- Handles pattern matching for different product types
"""

from decimal import Decimal

from app.services.shipping import calc_shipping, estimate_shopfans_shipping


def test_estimate_shopfans_hoodie_europe():
    """Test hoodie shipping calculation with Europe route."""
    # $150 order total → Europe route (30.86$/kg)
    quote = estimate_shopfans_shipping("Arc'teryx Hoodie", Decimal("150"))
    # 0.70kg * 30.86 = 21.60 + 3 handling = 24.60
    assert quote.cost_usd == Decimal("24.60")
    assert quote.weight_kg == Decimal("0.70")


def test_estimate_shopfans_hoodie_turkey():
    """Test hoodie shipping calculation with Turkey route."""
    # $250 order total → Turkey route (35.27$/kg)
    quote = estimate_shopfans_shipping("Arc'teryx Hoodie", Decimal("250"))
    # 0.70kg * 35.27 = 24.69 + 3 handling = 27.69
    assert quote.cost_usd == Decimal("27.69")
    assert quote.weight_kg == Decimal("0.70")


def test_estimate_shopfans_hoodie_kazakhstan():
    """Test hoodie shipping calculation with Kazakhstan route."""
    # $1200 order total → Kazakhstan route (41.89$/kg)
    quote = estimate_shopfans_shipping("Arc'teryx Hoodie", Decimal("1200"))
    # 0.70kg * 41.89 = 29.32 + 3 handling = 32.32
    assert quote.cost_usd == Decimal("32.32")
    assert quote.weight_kg == Decimal("0.70")


def test_estimate_shopfans_tee():
    """Test tee shirt shipping calculation."""
    # $150 order total → Europe route (30.86$/kg)
    quote = estimate_shopfans_shipping("Vintage Tee", Decimal("150"))
    # 0.20kg * 30.86 = 6.17, but min is 13.99 + 3 handling = 16.99
    assert quote.cost_usd == Decimal("16.99")
    assert quote.weight_kg == Decimal("0.20")


def test_estimate_shopfans_suitcase():
    """Test suitcase shipping calculation."""
    # $150 order total → Europe route (30.86$/kg)
    quote = estimate_shopfans_shipping("Large Suitcase", Decimal("150"))
    # 3.00kg * 30.86 = 92.58 + 5 handling (heavy) = 97.58
    assert quote.cost_usd == Decimal("97.58")
    assert quote.weight_kg == Decimal("3.00")


def test_estimate_shopfans_default():
    """Test default weight when no pattern matches."""
    # $150 order total → Europe route (30.86$/kg)
    quote = estimate_shopfans_shipping("Unknown Item", Decimal("150"))
    # 0.60kg * 30.86 = 18.52 + 3 handling = 21.52
    assert quote.cost_usd == Decimal("21.52")
    assert quote.weight_kg == Decimal("0.60")


def test_estimate_shopfans_empty_string():
    """Test empty string uses default weight."""
    # $150 order total → Europe route (30.86$/kg)
    quote = estimate_shopfans_shipping("", Decimal("150"))
    # 0.60kg * 30.86 = 18.52 + 3 handling = 21.52
    assert quote.cost_usd == Decimal("21.52")
    assert quote.weight_kg == Decimal("0.60")


def test_estimate_shopfans_case_insensitive():
    """Test that matching is case insensitive."""
    # $150 order total → Europe route (30.86$/kg)
    quote1 = estimate_shopfans_shipping("HOODIE", Decimal("150"))
    # 0.70kg * 30.86 = 21.60 + 3 handling = 24.60
    assert quote1.cost_usd == Decimal("24.60")

    quote2 = estimate_shopfans_shipping("vintage tee shirt", Decimal("150"))
    # 0.20kg * 30.86 = 6.17, but min is 13.99 + 3 handling = 16.99
    assert quote2.cost_usd == Decimal("16.99")


def test_estimate_shopfans_sneakers():
    """Test sneakers shipping calculation."""
    # $150 order total → Europe route (30.86$/kg)
    quote = estimate_shopfans_shipping("Nike Sneakers", Decimal("150"))
    # 1.40kg * 30.86 = 43.20 + 5 handling (heavy, > 1.36kg) = 48.20
    assert quote.cost_usd == Decimal("48.20")
    assert quote.weight_kg == Decimal("1.40")


def test_estimate_shopfans_boots():
    """Test boots shipping calculation."""
    # $150 order total → Europe route (30.86$/kg)
    quote = estimate_shopfans_shipping("Leather Boots", Decimal("150"))
    # 1.80kg * 30.86 = 55.55 + 5 handling (heavy, > 1.36kg) = 60.55
    assert quote.cost_usd == Decimal("60.55")
    assert quote.weight_kg == Decimal("1.80")


def test_estimate_shopfans_light_items():
    """Test light items that use $3 handling fee."""
    # $150 order total → Europe route (30.86$/kg)
    quote1 = estimate_shopfans_shipping("Tie", Decimal("150"))
    # 0.08kg * 30.86 = 2.47, but min is 13.99 + 3 handling = 16.99
    assert quote1.cost_usd == Decimal("16.99")
    assert quote1.weight_kg == Decimal("0.08")

    quote2 = estimate_shopfans_shipping("Socks", Decimal("150"))
    # 0.05kg * 30.86 = 1.54, but min is 13.99 + 3 handling = 16.99
    assert quote2.cost_usd == Decimal("16.99")
    assert quote2.weight_kg == Decimal("0.05")


def test_calc_shipping_russia():
    """Test shipping calculation for Russia."""
    # $150 order total → Europe route (30.86$/kg)
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


def test_route_thresholds():
    """Test that route selection works correctly at thresholds."""
    weight = Decimal("1.0")  # 1kg for consistent comparison
    
    # Europe route: < $200
    quote_europe = calc_shipping("russia", weight, Decimal("199.99"))
    # 1.0kg * 30.86 = 30.86 + 3 handling = 33.86
    assert quote_europe.cost_usd == Decimal("33.86")
    
    # Turkey route: >= $200
    quote_turkey = calc_shipping("russia", weight, Decimal("200.00"))
    # 1.0kg * 35.27 = 35.27 + 3 handling = 38.27
    assert quote_turkey.cost_usd == Decimal("38.27")
    
    # Kazakhstan route: >= $1000
    quote_kazakhstan = calc_shipping("russia", weight, Decimal("1000.00"))
    # 1.0kg * 41.89 = 41.89 + 3 handling = 44.89
    assert quote_kazakhstan.cost_usd == Decimal("44.89")


def test_weight_thresholds():
    """Test that handling fee calculation works correctly."""
    order_total = Decimal("150")  # Europe route
    
    # Light item: <= 1.36kg → $3 handling
    quote_light = calc_shipping("russia", Decimal("1.36"), order_total)
    # 1.36kg * 30.86 = 41.97 + 3 handling = 44.97
    assert quote_light.cost_usd == Decimal("44.97")
    
    # Heavy item: > 1.36kg → $5 handling
    quote_heavy = calc_shipping("russia", Decimal("1.37"), order_total)
    # 1.37kg * 30.86 = 42.28 + 5 handling = 47.28
    assert quote_heavy.cost_usd == Decimal("47.28")