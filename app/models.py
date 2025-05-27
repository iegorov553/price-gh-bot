"""Data models for the price bot application."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class ItemData(BaseModel):
    """Scraped item data."""
    price: Optional[Decimal] = None
    shipping_us: Optional[Decimal] = None
    is_buyable: bool = False
    title: Optional[str] = None


class SellerData(BaseModel):
    """Seller profile data."""
    num_reviews: int = 0
    avg_rating: float = 0.0
    trusted_badge: bool = False
    last_updated: datetime = Field(default_factory=lambda: datetime.now())


class ReliabilityScore(BaseModel):
    """Seller reliability evaluation result."""
    activity_score: int = 0
    rating_score: int = 0
    review_volume_score: int = 0
    badge_score: int = 0
    total_score: int = 0
    category: str = "Ghost"
    description: str = ""


class ShippingQuote(BaseModel):
    """Shipping cost estimation."""
    weight_kg: Decimal
    cost_usd: Decimal
    description: str = ""


class PriceCalculation(BaseModel):
    """Complete price calculation result."""
    item_price: Decimal
    shipping_us: Decimal = Decimal("0")
    shipping_russia: Decimal = Decimal("0")
    total_cost: Decimal
    commission: Decimal
    final_price_usd: Decimal
    final_price_rub: Optional[Decimal] = None
    exchange_rate: Optional[Decimal] = None


class CurrencyRate(BaseModel):
    """Currency exchange rate data."""
    from_currency: str
    to_currency: str
    rate: Decimal
    source: str
    fetched_at: datetime = Field(default_factory=datetime.now)
    markup_percentage: float = 0.0