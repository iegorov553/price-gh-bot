"""Shipping cost calculation service.

Provides Shopfans Lite shipping cost estimation for delivery to Russia based
on item title pattern matching and weight estimation. Uses configurable
pricing structure with handling fees and supports pattern-based categorization.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

from ..config import config
from ..models import ShippingQuote


def _calc_shopfans_price(weight: Decimal) -> Decimal:
    """Calculate Shopfans shipping cost based on item weight.
    
    Args:
        weight: Item weight in kilograms.
        
    Returns:
        Total shipping cost in USD including handling fees.
    """
    base = max(Decimal(str(config.shipping.base_cost)), Decimal(str(config.shipping.per_kg_rate)) * weight)

    if weight <= Decimal(str(config.shipping.light_threshold)):
        handling = Decimal(str(config.shipping.light_handling_fee))
    else:
        handling = Decimal(str(config.shipping.heavy_handling_fee))

    return (base + handling).quantize(Decimal("0.01"), ROUND_HALF_UP)


def estimate_shopfans_shipping(title: str) -> ShippingQuote:
    """Estimate Shopfans shipping cost based on item title.
    
    Analyzes item title against configured patterns to estimate weight,
    then calculates shipping cost using Shopfans Lite pricing structure.
    Falls back to default weight if no patterns match.
    
    Args:
        title: Item title/description to analyze for weight estimation.
    
    Returns:
        ShippingQuote with estimated weight, cost, and description.
    """
    if not title:
        title = ""

    title_lc = title.lower()

    # Try to match patterns from config
    for pattern_data in config.shipping_patterns:
        pattern = pattern_data.get("pattern", "")
        weight = Decimal(str(pattern_data.get("weight", config.default_shipping_weight)))

        if re.search(pattern, title_lc, re.IGNORECASE):
            cost = _calc_shopfans_price(weight)
            return ShippingQuote(
                weight_kg=weight,
                cost_usd=cost,
                description=f"Matched pattern: {pattern}"
            )

    # Use default weight if no pattern matches
    default_weight = Decimal(str(config.default_shipping_weight))
    cost = _calc_shopfans_price(default_weight)

    return ShippingQuote(
        weight_kg=default_weight,
        cost_usd=cost,
        description="Default weight used (no pattern match)"
    )


def calc_shipping(country: str, weight: Decimal) -> ShippingQuote:
    """Calculate shipping cost for a specific country and weight.
    
    Calculates shipping costs using the Shopfans pricing structure for
    supported countries. Currently only supports shipping to Russia.
    For unsupported countries, returns zero cost.
    
    Args:
        country: Target country for shipping calculation. Case-insensitive.
                Only "russia" is currently supported.
        weight: Item weight in kilograms. Must be a positive Decimal value.
    
    Returns:
        ShippingQuote containing the calculated cost, weight, and description
        of the shipping calculation method used.
    """
    if country.lower() == "russia":
        cost = _calc_shopfans_price(weight)
        return ShippingQuote(
            weight_kg=weight,
            cost_usd=cost,
            description="Shopfans shipping to Russia"
        )

    # Fallback for unsupported countries
    return ShippingQuote(
        weight_kg=weight,
        cost_usd=Decimal("0"),
        description=f"Shipping to {country} not supported"
    )
