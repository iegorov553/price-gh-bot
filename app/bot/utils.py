"""Bot utility functions and response formatting.

Provides utility functions for Telegram bot operations including admin
notifications, price calculation logic, response message formatting, and
HTTP session management. Centralizes reusable bot functionality.
"""

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import aiohttp
from telegram.ext import Application

from ..config import config
from ..models import CurrencyRate, PriceCalculation, ReliabilityScore
from .messages import (
    ADMIN_NOTIFICATION,
    COMMISSION_LINE,
    COMMISSION_TYPE_FIXED,
    COMMISSION_TYPE_PERCENTAGE,
    FINAL_TOTAL_LINE,
    ITEM_PRICE_LINE,
    NO_BADGE,
    PRICE_CALCULATION_HEADER,
    RUB_CONVERSION_LINE,
    SELLER_ACTIVITY_LINE,
    SELLER_BADGE_LINE,
    SELLER_DESCRIPTION_LINE,
    SELLER_DETAILS_HEADER,
    SELLER_INFO_LINE,
    SELLER_PROFILE_HEADER,
    SELLER_RATING_LINE,
    SELLER_RELIABILITY,
    SELLER_RELIABILITY_LINE,
    SELLER_REVIEWS_LINE,
    SEPARATOR_LINE,
    SHIPPING_ONLY_RU_LINE,
    SHIPPING_RU_LINE,
    SHIPPING_US_LINE,
    SUBTOTAL_LINE,
    TIME_DAYS_AGO,
    TIME_TODAY,
    TIME_YESTERDAY,
    TRUSTED_SELLER_BADGE,
)

logger = logging.getLogger(__name__)


async def notify_admin(application: Application, message: str) -> None:
    """Send notification to admin about system issues.

    Args:
        application: Telegram Application instance for sending messages.
        message: Alert message to send to admin.
    """
    try:
        await application.bot.send_message(
            chat_id=config.bot.admin_chat_id,
            text=ADMIN_NOTIFICATION.format(message=message)
        )
        logger.info(f"Admin notification sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")


async def send_debug_to_admin(application: Application, message: str) -> None:
    """Send debug message to admin for troubleshooting purposes.

    Args:
        application: Telegram Application instance for sending messages.
        message: Debug message content to send to admin.
    """
    try:
        await application.bot.send_message(
            chat_id=config.bot.admin_chat_id,
            text=f"🔧 Debug: {message}"
        )
    except Exception as e:
        logger.debug(f"Failed to send debug message to admin: {e}")


def calculate_final_price(item_price: Decimal, shipping_us: Decimal, shipping_russia: Decimal) -> PriceCalculation:
    """Calculate final price with tiered commission structure.

    Applies either fixed commission ($15) for items under $150 or 10% markup
    for items $150 and above. Commission is calculated from item price plus
    US shipping cost (both values from the listing).

    Args:
        item_price: Base price of the item in USD.
        shipping_us: US domestic shipping cost in USD.
        shipping_russia: Russia delivery shipping cost in USD.

    Returns:
        PriceCalculation: Complete price breakdown including commission and final price.
    """
    total_cost = item_price + shipping_us + shipping_russia

    # Commission base includes item price + US shipping (both from listing)
    commission_base = item_price + shipping_us

    # Apply commission based on item price + US shipping
    if commission_base < Decimal(str(config.commission.fixed_threshold)):
        commission = Decimal(str(config.commission.fixed_amount))
        final_price = (total_cost + commission).quantize(Decimal('0.01'), ROUND_HALF_UP)
    else:
        commission_rate = Decimal(str(config.commission.percentage_rate))
        commission = (commission_base * commission_rate).quantize(Decimal('0.01'), ROUND_HALF_UP)
        final_price = (total_cost + commission).quantize(Decimal('0.01'), ROUND_HALF_UP)

    return PriceCalculation(
        item_price=item_price,
        shipping_us=shipping_us,
        shipping_russia=shipping_russia,
        total_cost=total_cost,
        commission=commission,
        final_price_usd=final_price
    )


def format_price_response(
    calculation: PriceCalculation,
    exchange_rate: CurrencyRate | None = None,
    reliability: ReliabilityScore | None = None,
    is_grailed: bool = False
) -> str:
    """Format price calculation into user-friendly response message.

    Creates formatted message with clear price breakdown showing each component
    separately for better readability and understanding.

    Args:
        calculation: Price calculation data including all cost components.
        exchange_rate: USD to RUB exchange rate for currency conversion.
        reliability: Seller reliability score for Grailed items.
        is_grailed: Whether this is a Grailed listing to show seller info.

    Returns:
        str: Formatted message ready to send to user.
    """
    # Start with header
    response_lines = [PRICE_CALCULATION_HEADER, ""]

    # Item price
    response_lines.append(ITEM_PRICE_LINE.format(item_price=calculation.item_price))

    # Shipping breakdown
    if calculation.shipping_us == 0:
        # Only Russia shipping (direct from seller or Shopfans)
        response_lines.append(SHIPPING_ONLY_RU_LINE.format(shipping_ru=calculation.shipping_russia))
    else:
        # Both US and Russia shipping
        response_lines.append(SHIPPING_US_LINE.format(shipping_us=calculation.shipping_us))
        response_lines.append(SHIPPING_RU_LINE.format(shipping_ru=calculation.shipping_russia))

    # Subtotal
    response_lines.append(SUBTOTAL_LINE.format(subtotal=calculation.total_cost))
    response_lines.append("")  # Empty line before commission

    # Commission
    if calculation.item_price < Decimal(str(config.commission.fixed_threshold)):
        commission_type = COMMISSION_TYPE_FIXED
    else:
        commission_type = COMMISSION_TYPE_PERCENTAGE

    response_lines.append(COMMISSION_LINE.format(
        commission=calculation.commission,
        commission_type=commission_type
    ))

    # Separator and final total
    response_lines.append(SEPARATOR_LINE)
    response_lines.append(FINAL_TOTAL_LINE.format(final_price=calculation.final_price_usd))

    # RUB conversion if available
    if exchange_rate:
        final_price_rub = (calculation.final_price_usd * exchange_rate.rate).quantize(Decimal('0.01'), ROUND_HALF_UP)
        response_lines.append(RUB_CONVERSION_LINE.format(rub_price=final_price_rub))

    # Add seller reliability for Grailed items
    if reliability and is_grailed:
        emoji = SELLER_RELIABILITY.get(reliability.category, {}).get('emoji', '❓')

        response_lines.append("")  # Empty line before seller info
        response_lines.append(SELLER_INFO_LINE.format(
            emoji=emoji,
            category=reliability.category,
            total_score=reliability.total_score
        ))
        response_lines.append(SELLER_DESCRIPTION_LINE.format(
            description=reliability.description
        ))

    return "\n".join(response_lines)


def format_seller_profile_response(seller_data: dict) -> str:
    """Format Grailed seller profile analysis into detailed message.

    Creates comprehensive seller reliability breakdown including activity,
    rating, review volume, and badge status with user-friendly formatting.

    Args:
        seller_data: Dictionary containing seller profile data with reliability
                    scores, last update timestamp, and badge status.

    Returns:
        str: Formatted seller analysis message in Russian.
    """
    reliability = seller_data['reliability']
    emoji = SELLER_RELIABILITY.get(reliability['category'], {}).get('emoji', '❓')

    # Calculate days since last update
    days_since_update = (datetime.now(UTC) - seller_data['last_updated']).days

    # Format last update text
    if days_since_update == 0:
        last_update_text = TIME_TODAY
    elif days_since_update == 1:
        last_update_text = TIME_YESTERDAY
    else:
        last_update_text = TIME_DAYS_AGO.format(days=days_since_update)

    # Badge text
    badge_text = TRUSTED_SELLER_BADGE if seller_data['trusted_badge'] else NO_BADGE

    response_lines = [
        SELLER_PROFILE_HEADER,
        "",
        SELLER_RELIABILITY_LINE.format(
            emoji=emoji,
            category=reliability['category'],
            total_score=reliability['total_score']
        ),
        reliability['description'],
        "",
        SELLER_DETAILS_HEADER,
        SELLER_ACTIVITY_LINE.format(
            activity_score=reliability['activity_score'],
            last_update_text=last_update_text
        ),
        SELLER_RATING_LINE.format(
            rating_score=reliability['rating_score'],
            avg_rating=seller_data['avg_rating']
        ),
        SELLER_REVIEWS_LINE.format(
            review_volume_score=reliability['review_volume_score'],
            num_reviews=seller_data['num_reviews']
        ),
        SELLER_BADGE_LINE.format(
            badge_score=reliability['badge_score'],
            badge_text=badge_text
        ),
    ]

    return "\n".join(response_lines)


def create_session() -> aiohttp.ClientSession:
    """Create configured aiohttp session for web scraping.

    Sets up session with connection limits, timeouts, and user agent
    header optimized for reliable web scraping operations.

    Returns:
        aiohttp.ClientSession: Configured HTTP session for making requests.
    """
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
    timeout = aiohttp.ClientTimeout(total=config.bot.timeout)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PriceBot/2.0)"}

    return aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers=headers
    )
