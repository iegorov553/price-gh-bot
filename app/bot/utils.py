"""Bot utility functions."""

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import aiohttp
from telegram import Application

from ..config import config
from ..models import PriceCalculation, CurrencyRate, ReliabilityScore
from messages import (
    PRICE_LINE, FINAL_PRICE_LINE, COMMISSION_FIXED, COMMISSION_PERCENTAGE,
    SELLER_INFO_LINE, SELLER_DESCRIPTION_LINE, SELLER_RELIABILITY,
    SELLER_PROFILE_HEADER, SELLER_RELIABILITY_LINE, SELLER_DETAILS_HEADER,
    SELLER_ACTIVITY_LINE, SELLER_RATING_LINE, SELLER_REVIEWS_LINE,
    SELLER_BADGE_LINE, TRUSTED_SELLER_BADGE, NO_BADGE, TIME_TODAY,
    TIME_YESTERDAY, TIME_DAYS_AGO, ADMIN_NOTIFICATION
)

logger = logging.getLogger(__name__)


async def notify_admin(application: Application, message: str) -> None:
    """Send notification to admin about API failure."""
    try:
        await application.bot.send_message(
            chat_id=config.bot.admin_chat_id,
            text=ADMIN_NOTIFICATION.format(message=message)
        )
        logger.info(f"Admin notification sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")


async def send_debug_to_admin(application: Application, message: str) -> None:
    """Send debug message to admin only (not to users)."""
    try:
        await application.bot.send_message(
            chat_id=config.bot.admin_chat_id,
            text=f"🔧 Debug: {message}"
        )
    except Exception as e:
        logger.debug(f"Failed to send debug message to admin: {e}")


def calculate_final_price(item_price: Decimal, shipping_us: Decimal, shipping_russia: Decimal) -> PriceCalculation:
    """Calculate final price with commission."""
    total_cost = item_price + shipping_us + shipping_russia
    
    # Apply commission based on item price
    if item_price < Decimal(str(config.commission.fixed_threshold)):
        commission = Decimal(str(config.commission.fixed_amount))
        final_price = (total_cost + commission).quantize(Decimal('0.01'), ROUND_HALF_UP)
    else:
        commission_rate = Decimal(str(config.commission.percentage_rate))
        commission = (total_cost * commission_rate).quantize(Decimal('0.01'), ROUND_HALF_UP)
        final_price = (total_cost * (Decimal('1') + commission_rate)).quantize(Decimal('0.01'), ROUND_HALF_UP)
    
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
    exchange_rate: Optional[CurrencyRate] = None,
    reliability: Optional[ReliabilityScore] = None,
    is_grailed: bool = False
) -> str:
    """Format price calculation into user response."""
    # Prepare shipping text
    if calculation.shipping_us == 0:
        shipping_text = f" + ${calculation.shipping_russia} доставка (Shopfans)"
    else:
        shipping_text = (
            f" + ${calculation.shipping_us} доставка по США"
            f" + ${calculation.shipping_russia} доставка РФ"
        )
    
    # Commission text
    if calculation.item_price < Decimal(str(config.commission.fixed_threshold)):
        commission_text = COMMISSION_FIXED
    else:
        commission_text = COMMISSION_PERCENTAGE
    
    # Convert to RUB if rate available
    rub_text = ""
    if exchange_rate:
        final_price_rub = (calculation.final_price_usd * exchange_rate.rate).quantize(Decimal('0.01'), ROUND_HALF_UP)
        rub_text = f" (₽{final_price_rub})"
    
    # Base response
    response_lines = [
        PRICE_LINE.format(
            price=calculation.item_price,
            shipping_text=shipping_text,
            total_cost=calculation.total_cost
        ),
        FINAL_PRICE_LINE.format(
            commission_text=commission_text,
            final_price=calculation.final_price_usd,
            rub_text=rub_text
        )
    ]
    
    # Add seller reliability for Grailed items
    if reliability and is_grailed:
        emoji = SELLER_RELIABILITY.get(reliability.category, {}).get('emoji', '❓')
        
        response_lines.append("")  # Empty line
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
    """Format seller profile analysis into readable message."""
    reliability = seller_data['reliability']
    emoji = SELLER_RELIABILITY.get(reliability['category'], {}).get('emoji', '❓')
    
    # Calculate days since last update
    days_since_update = (datetime.now(timezone.utc) - seller_data['last_updated']).days
    
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
        SELLER_PROFILE_HEADER.format(emoji=emoji),
        "",
        SELLER_RELIABILITY_LINE.format(
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
    """Create aiohttp session with proper configuration."""
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
    timeout = aiohttp.ClientTimeout(total=config.bot.timeout)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PriceBot/2.0)"}
    
    return aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers=headers
    )