"""Data models for the price bot application.

Defines Pydantic models for all data structures used throughout the application
including scraped item data, seller information, pricing calculations, and
external API responses. All models include validation and type checking.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, Field


class ItemData(BaseModel):
    """Scraped marketplace item data.

    Attributes:
        price: Item price in USD, None if not found.
        shipping_us: US domestic shipping cost in USD, None if not found.
        is_buyable: Whether item has fixed buy-now price vs offer-only.
        title: Item title/description for shipping weight estimation.
        image_url: Primary product image URL for display in messages.
    """
    price: Decimal | None = None
    shipping_us: Decimal | None = None
    is_buyable: bool = False
    title: str | None = None
    image_url: str | None = None


class SellerData(BaseModel):
    """Seller profile information from marketplace.

    Attributes:
        num_reviews: Total number of seller reviews.
        avg_rating: Average seller rating (0.0-5.0 scale).
        trusted_badge: Whether seller has verified/trusted status.
        last_updated: When seller profile was last updated.
    """
    num_reviews: int = 0
    avg_rating: float = 0.0
    trusted_badge: bool = False
    last_updated: datetime = Field(default_factory=lambda: datetime.now())


class ReliabilityScore(BaseModel):
    """Calculated seller reliability evaluation.

    Attributes:
        activity_score: Points for recent activity (0-30).
        rating_score: Points for high ratings (0-35).
        review_volume_score: Points for review count (0-25).
        badge_score: Points for trusted status (0-10).
        total_score: Sum of all scores (0-100).
        category: Reliability tier (Diamond/Gold/Silver/Bronze/Ghost).
        description: Human-readable category explanation.
    """
    activity_score: int = 0
    rating_score: int = 0
    review_volume_score: int = 0
    badge_score: int = 0
    total_score: int = 0
    category: str = "Ghost"
    description: str = ""


class ShippingQuote(BaseModel):
    """Estimated shipping cost calculation.

    Attributes:
        weight_kg: Estimated item weight in kilograms.
        cost_usd: Calculated shipping cost in USD.
        description: Explanation of how cost was determined.
    """
    weight_kg: Decimal
    cost_usd: Decimal
    description: str = ""


class PriceCalculation(BaseModel):
    """Complete price breakdown with new structured format.

    New structure supports:
    - Intermediate subtotal (item + US shipping + commission)
    - Additional costs (RF customs duty + RF shipping)
    - Final total (subtotal + additional costs)

    Attributes:
        item_price: Original item price in USD.
        shipping_us: US domestic shipping cost.
        commission: Applied commission fee.
        commission_type: Type of commission ("fixed" or "percentage").
        subtotal: Item + US shipping + commission.
        customs_duty: Russian customs duty (15% over 200 EUR).
        shipping_russia: Russia delivery cost via Shopfans.
        additional_costs: Customs duty + Russia shipping.
        final_price_usd: Subtotal + additional costs.
        final_price_rub: Final price converted to rubles (if available).
        exchange_rate: USD to RUB rate used for conversion.
    """
    item_price: Decimal
    shipping_us: Decimal = Decimal("0")
    commission: Decimal
    commission_type: str = "fixed"  # "fixed" or "percentage"
    subtotal: Decimal
    customs_duty: Decimal = Decimal("0")
    shipping_russia: Decimal = Decimal("0")
    additional_costs: Decimal
    final_price_usd: Decimal
    final_price_rub: Decimal | None = None
    exchange_rate: Decimal | None = None

    @property
    def total_cost(self) -> Decimal:
        """Legacy compatibility: item + US shipping + Russia shipping."""
        return (self.item_price + self.shipping_us + self.shipping_russia).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )


class CurrencyRate(BaseModel):
    """Exchange rate data from external API.

    Attributes:
        from_currency: Source currency code (e.g., 'USD').
        to_currency: Target currency code (e.g., 'RUB').
        rate: Exchange rate multiplier.
        source: API source identifier (e.g., 'cbr').
        fetched_at: When rate was retrieved.
        markup_percentage: Applied markup over base rate.
    """
    from_currency: str
    to_currency: str
    rate: Decimal
    source: str
    fetched_at: datetime = Field(default_factory=datetime.now)
    markup_percentage: float = 0.0


class SearchAnalytics(BaseModel):
    """Analytics data for user search queries.

    Stores comprehensive information about each user interaction with the bot
    including URL processing, pricing results, seller analysis, and performance
    metrics for business intelligence and optimization purposes.

    Attributes:
        url: The original URL requested by user.
        user_id: Telegram user ID who made the request.
        username: Telegram username (if available).
        timestamp: When the request was processed.
        platform: Marketplace platform ('ebay', 'grailed', 'profile').
        success: Whether URL processing completed successfully.
        item_price: Extracted item price in USD (if found).
        shipping_us: US domestic shipping cost in USD (if found).
        item_title: Product title/description (if extracted).
        error_message: Error details if processing failed.
        processing_time_ms: Total processing time in milliseconds.
        seller_score: Calculated seller reliability score (0-100).
        seller_category: Seller reliability category (Diamond/Gold/etc).
        final_price_usd: Complete calculated price in USD.
        commission: Applied commission fee in USD.
        is_buyable: Whether item has fixed buy-now pricing.
    """
    url: str
    user_id: int
    username: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    platform: str  # 'ebay', 'grailed', 'profile'
    success: bool
    item_price: Decimal | None = None
    shipping_us: Decimal | None = None
    item_title: str | None = None
    error_message: str | None = None
    processing_time_ms: int | None = None
    seller_score: int | None = None
    seller_category: str | None = None
    final_price_usd: Decimal | None = None
    commission: Decimal | None = None
    is_buyable: bool | None = None
