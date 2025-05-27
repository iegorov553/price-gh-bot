"""Shipping cost calculation service."""

import re
from decimal import Decimal, ROUND_HALF_UP

from ..config import config
from ..models import ShippingQuote


def _calc_shopfans_price(weight: Decimal) -> Decimal:
    """Calculate Shopfans shipping cost based on weight."""
    base = max(Decimal(str(config.shipping.base_cost)), Decimal(str(config.shipping.per_kg_rate)) * weight)
    
    if weight <= Decimal(str(config.shipping.light_threshold)):
        handling = Decimal(str(config.shipping.light_handling_fee))
    else:
        handling = Decimal(str(config.shipping.heavy_handling_fee))
    
    return (base + handling).quantize(Decimal("0.01"), ROUND_HALF_UP)


def estimate_shopfans_shipping(title: str) -> ShippingQuote:
    """
    Estimate Shopfans shipping cost based on item title.
    
    Args:
        title: Item title to analyze
    
    Returns:
        ShippingQuote with estimated cost and weight
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
    """
    Calculate shipping cost for a specific country and weight.
    
    Args:
        country: Target country (currently only "russia" supported)
        weight: Item weight in kg
    
    Returns:
        ShippingQuote with cost calculation
    """
    if country.lower() == "russia":
        cost = _calc_shopfans_price(weight)
        return ShippingQuote(
            weight_kg=weight,
            cost_usd=cost,
            description=f"Shopfans shipping to Russia"
        )
    
    # Fallback for unsupported countries
    return ShippingQuote(
        weight_kg=weight,
        cost_usd=Decimal("0"),
        description=f"Shipping to {country} not supported"
    )