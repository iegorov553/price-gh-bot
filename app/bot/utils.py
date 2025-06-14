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
    CUSTOMS_DUTY_LINE,
    FINAL_TOTAL_HEADER,
    FINAL_TOTAL_LINE_NO_RUB,
    ITEM_PRICE_LINE,
    NO_BADGE,
    RUSSIA_COSTS_LINE,
    RUSSIA_IMPORT_HEADER,
    SELLER_ACTIVITY_LINE,
    SELLER_BADGE_LINE,
    SELLER_DESCRIPTION_LINE,
    SELLER_DETAILS_HEADER,
    SELLER_PROFILE_HEADER,
    SELLER_RATING_LINE,
    SELLER_RELIABILITY,
    SELLER_RELIABILITY_LINE,
    SELLER_REVIEWS_LINE,
    SHIPPING_ONLY_RU_LINE,
    SHIPPING_RU_LINE,
    SHIPPING_US_LINE,
    TIME_DAYS_AGO,
    TIME_TODAY,
    TIME_YESTERDAY,
    TRUSTED_SELLER_BADGE,
    USA_PURCHASE_HEADER,
    USA_SUBTOTAL_LINE,
)

logger = logging.getLogger(__name__)


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for MarkdownV2 format.

    Escapes characters that have special meaning in Telegram's MarkdownV2:
    _*[]()~`>#+-=|{}.!

    Note: This function preserves markdown links in format [text](url)
    but escapes special characters within link text and URLs.

    Args:
        text: Text to escape

    Returns:
        Escaped text safe for MarkdownV2
    """
    import re

    # Characters that need escaping in MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'

    def escape_chars_in_text(text_to_escape: str) -> str:
        """Escape special characters in text."""
        for char in escape_chars:
            text_to_escape = text_to_escape.replace(char, f'\\{char}')
        return text_to_escape

    def process_link(match) -> str:
        """Process markdown link - escape special chars in text and URL."""
        link_text = match.group(1)
        link_url = match.group(2)
        
        # Escape special characters in link text (but not brackets/parentheses that are part of markdown)
        escaped_text = escape_chars_in_text(link_text)
        
        # URLs don't need escaping in MarkdownV2 when inside parentheses
        return f"[{escaped_text}]({link_url})"

    # Process markdown links first
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', process_link, text)

    # Then escape special characters in remaining text (outside of links)
    def escape_non_link_text(text_to_process: str) -> str:
        """Escape text that's not part of markdown links."""
        # Split by markdown links to process only text outside links
        parts = re.split(r'(\[[^\]]+\]\([^)]+\))', text_to_process)
        
        for i in range(len(parts)):
            # Only escape odd indices (text between links) and first/last if not links
            if i % 2 == 0:  # Even indices are text outside links
                parts[i] = escape_chars_in_text(parts[i])
        
        return ''.join(parts)
    
    return escape_non_link_text(text)


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


async def calculate_final_price(
    item_price: Decimal,
    shipping_us: Decimal,
    shipping_russia: Decimal,
    session: aiohttp.ClientSession
) -> PriceCalculation:
    """Calculate final price with new structured breakdown including RF customs duty.

    New calculation structure:
    1. Item + US shipping + commission = Subtotal
    2. RF customs duty + RF shipping = Additional costs
    3. Subtotal + Additional costs = Final total

    Commission is calculated from item price + US shipping (both values from listing).
    RF customs duty applies 15% on amount exceeding 200 EUR threshold.

    Args:
        item_price: Base price of the item in USD.
        shipping_us: US domestic shipping cost in USD.
        shipping_russia: Russia delivery shipping cost in USD.
        session: aiohttp session for currency API requests.

    Returns:
        PriceCalculation: Complete price breakdown with new structured format.
    """
    # Commission base includes item price + US shipping (both from listing)
    commission_base = item_price + shipping_us

    # Apply commission based on item price + US shipping
    if commission_base < Decimal(str(config.commission.fixed_threshold)):
        commission = Decimal(str(config.commission.fixed_amount))
        commission_type = "fixed"
    else:
        commission_rate = Decimal(str(config.commission.percentage_rate))
        commission = (commission_base * commission_rate).quantize(Decimal('0.01'), ROUND_HALF_UP)
        commission_type = "percentage"

    # Calculate subtotal: item + US shipping + commission
    subtotal = (item_price + shipping_us + commission).quantize(Decimal('0.01'), ROUND_HALF_UP)

    # Calculate RF customs duty
    from ..services.customs import calculate_rf_customs_duty
    customs_duty = await calculate_rf_customs_duty(item_price, shipping_us, session)

    # Calculate additional costs: customs duty + RF shipping
    additional_costs = (customs_duty + shipping_russia).quantize(Decimal('0.01'), ROUND_HALF_UP)

    # Calculate final total: subtotal + additional costs
    final_price = (subtotal + additional_costs).quantize(Decimal('0.01'), ROUND_HALF_UP)

    return PriceCalculation(
        item_price=item_price,
        shipping_us=shipping_us,
        commission=commission,
        commission_type=commission_type,
        subtotal=subtotal,
        customs_duty=customs_duty,
        shipping_russia=shipping_russia,
        additional_costs=additional_costs,
        final_price_usd=final_price
    )


def format_price_response(
    calculation: PriceCalculation,
    exchange_rate: CurrencyRate | None = None,
    reliability: ReliabilityScore | None = None,
    is_grailed: bool = False,
    item_title: str | None = None,
    item_url: str | None = None,
    use_markdown: bool = False
) -> str:
    """Format price calculation into user-friendly response with grouped stages format.

    Creates formatted message using grouped stages breakdown:
    1. Item title with hyperlink (if available)
    2. USA PURCHASE section with item, shipping, commission
    3. RUSSIA IMPORT section with customs duty and shipping
    4. Final total with RUB conversion
    5. Seller info (for Grailed)

    Args:
        calculation: Price calculation data with structured format.
        exchange_rate: USD to RUB exchange rate for currency conversion.
        reliability: Seller reliability score for Grailed items.
        is_grailed: Whether this is a Grailed listing to show seller info.
        item_title: Item title to display with hyperlink.
        item_url: Item URL for hyperlink.
        use_markdown: Whether to escape text for MarkdownV2 format.

    Returns:
        str: Formatted message ready to send to user.
    """
    response_lines = []

    # Item title with hyperlink if available
    if item_title and item_url:
        response_lines.extend([
            f"📦 [{item_title}]({item_url})",
            ""
        ])

    # USA PURCHASE section
    response_lines.append(USA_PURCHASE_HEADER)
    response_lines.append(ITEM_PRICE_LINE.format(item_price=calculation.item_price))
    
    # US shipping (if exists)
    if calculation.shipping_us > 0:
        response_lines.append(SHIPPING_US_LINE.format(shipping_us=calculation.shipping_us))
    
    # Commission
    commission_type = COMMISSION_TYPE_FIXED if calculation.commission_type == "fixed" else COMMISSION_TYPE_PERCENTAGE
    response_lines.append(COMMISSION_LINE.format(
        commission=calculation.commission,
        commission_type=commission_type
    ))
    response_lines.append(USA_SUBTOTAL_LINE.format(subtotal=calculation.subtotal))
    response_lines.append("")  # Empty line

    # RUSSIA IMPORT section (only if there are additional costs)
    if calculation.additional_costs > 0:
        response_lines.append(RUSSIA_IMPORT_HEADER)
        
        # RF customs duty (if applicable)
        if calculation.customs_duty > 0:
            response_lines.append(CUSTOMS_DUTY_LINE.format(customs_duty=calculation.customs_duty))
        
        # RF shipping
        if calculation.shipping_us == 0:
            # Only Russia shipping (direct from seller or Shopfans)
            response_lines.append(SHIPPING_ONLY_RU_LINE.format(shipping_ru=calculation.shipping_russia))
        else:
            # Russia shipping when US shipping also exists
            response_lines.append(SHIPPING_RU_LINE.format(shipping_ru=calculation.shipping_russia))
        
        response_lines.append(RUSSIA_COSTS_LINE.format(additional_costs=calculation.additional_costs))
        response_lines.append("")  # Empty line

    # Final total with RUB conversion
    if exchange_rate:
        final_price_rub = (calculation.final_price_usd * exchange_rate.rate).quantize(Decimal('0.01'), ROUND_HALF_UP)
        response_lines.append(FINAL_TOTAL_HEADER.format(
            final_price=calculation.final_price_usd,
            rub_price=final_price_rub
        ))
    else:
        response_lines.append(FINAL_TOTAL_LINE_NO_RUB.format(final_price=calculation.final_price_usd))

    # Add seller reliability for Grailed items
    if reliability and is_grailed:
        emoji = SELLER_RELIABILITY.get(reliability.category, {}).get('emoji', '❓')

        response_lines.append("")  # Empty line before seller info
        response_lines.append(f"👤 Продавец: {emoji} {reliability.category} ({reliability.total_score}/100)")

    response = "\n".join(response_lines)

    # Apply MarkdownV2 escaping if needed
    if use_markdown:
        response = escape_markdown_v2(response)

    return response


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
