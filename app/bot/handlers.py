"""Telegram bot handlers."""

import asyncio
import logging
import re
from urllib.parse import urlparse

import aiohttp
from telegram import Update
from telegram.ext import ContextTypes
from bs4 import BeautifulSoup

from ..scrapers import ebay, grailed
from ..services import currency, shipping, reliability
from ..models import SellerData
from .utils import (
    notify_admin, send_debug_to_admin, calculate_final_price, 
    format_price_response, format_seller_profile_response, create_session
)
from ..bot.messages import (
    START_MESSAGE, ERROR_PRICE_NOT_FOUND, ERROR_SELLER_DATA_NOT_FOUND,
    ERROR_SELLER_ANALYSIS, OFFER_ONLY_MESSAGE, LOG_CBR_API_FAILED
)

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(START_MESSAGE)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages containing URLs."""
    text = update.message.text or ''
    urls = re.findall(r"(https?://[\w\.-]+(?:/[^\s]*)?)", text)
    if not urls:
        return
    
    async with create_session() as session:
        # Check for Grailed seller profiles first
        for url in urls:
            logger.info(f"Checking URL: {url}")
            if grailed.is_grailed_seller_profile(url):
                logger.info(f"Processing seller profile: {url}")
                await _handle_seller_profile(update, context, url, session)
                return  # Exit after processing seller profile
        
        # Process regular listings
        await _handle_listings(update, context, urls, session)


async def _handle_seller_profile(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    profile_url: str, 
    session: aiohttp.ClientSession
) -> None:
    """Handle Grailed seller profile analysis."""
    try:
        seller_analysis = await grailed.analyze_seller_profile(profile_url, session)
        if seller_analysis:
            # Add reliability evaluation
            seller_data = SellerData(
                num_reviews=seller_analysis['num_reviews'],
                avg_rating=seller_analysis['avg_rating'],
                trusted_badge=seller_analysis['trusted_badge'],
                last_updated=seller_analysis['last_updated']
            )
            
            reliability_score = reliability.evaluate_seller_reliability(seller_data)
            seller_analysis['reliability'] = reliability_score.dict()
            
            response = format_seller_profile_response(seller_analysis)
            await update.message.reply_text(response)
        else:
            await update.message.reply_text(ERROR_SELLER_DATA_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error processing seller profile {profile_url}: {e}")
        await update.message.reply_text(ERROR_SELLER_ANALYSIS)
        await send_debug_to_admin(context.application, f"Seller profile error for {profile_url}: {e}")


async def _handle_listings(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    urls: list, 
    session: aiohttp.ClientSession
) -> None:
    """Handle regular marketplace listings."""
    # Resolve Grailed app.link shorteners
    resolved_urls = []
    for url in urls:
        resolved_url = await _resolve_shortener(url, session)
        resolved_urls.append(resolved_url)
    
    # Fetch all URLs concurrently
    tasks = []
    for url in resolved_urls:
        if ebay.is_ebay_url(url):
            tasks.append(_scrape_ebay_item(url, session))
        elif grailed.is_grailed_url(url):
            tasks.append(_scrape_grailed_item(url, session))
        else:
            tasks.append(asyncio.create_task(_return_none()))
    
    results = await asyncio.gather(*tasks)
    
    # Get exchange rate once for all conversions
    logger.info("Getting USD to RUB exchange rate...")
    exchange_rate = await currency.get_usd_to_rub_rate(session)
    
    if exchange_rate:
        logger.info(f"Successfully got exchange rate: {exchange_rate.rate}")
    else:
        logger.error("CBR API failed - currency conversion unavailable")
        await notify_admin(context.application, LOG_CBR_API_FAILED)
    
    # Process results
    for url, result in zip(resolved_urls, results):
        if result is None:
            continue
            
        item_data, seller_data = result
        
        if not item_data.price:
            await update.message.reply_text(ERROR_PRICE_NOT_FOUND)
            continue
        
        if not item_data.is_buyable:
            # For offer-only items
            await update.message.reply_text(
                OFFER_ONLY_MESSAGE.format(price=item_data.price)
            )
            continue
        
        # Calculate shipping and final price
        shopfans_quote = shipping.estimate_shopfans_shipping(item_data.title or "")
        calculation = calculate_final_price(
            item_data.price,
            item_data.shipping_us or 0,
            shopfans_quote.cost_usd
        )
        
        # Add exchange rate if available
        if exchange_rate:
            calculation.exchange_rate = exchange_rate.rate
            calculation.final_price_rub = (calculation.final_price_usd * exchange_rate.rate)
        
        # Evaluate seller reliability for Grailed
        reliability_score = None
        is_grailed_item = grailed.is_grailed_url(url)
        
        if seller_data and is_grailed_item:
            try:
                reliability_score = reliability.evaluate_seller_reliability(seller_data)
                logger.info(f"Seller reliability: {reliability_score.category} ({reliability_score.total_score}/100)")
            except Exception as e:
                logger.error(f"Error evaluating seller reliability: {e}")
        elif is_grailed_item:
            logger.warning(f"No seller data found for Grailed item: {url}")
            await send_debug_to_admin(context.application, f"No seller data extracted for Grailed item: {url}")
        
        # Format and send response
        response = format_price_response(
            calculation, 
            exchange_rate, 
            reliability_score, 
            is_grailed_item
        )
        await update.message.reply_text(response)


async def _resolve_shortener(url: str, session: aiohttp.ClientSession) -> str:
    """Resolve Grailed app.link shorteners."""
    parsed = urlparse(url)
    if not parsed.netloc.endswith('app.link'):
        return url
    
    try:
        async with session.get(url, timeout=20) as response:
            if response.url and 'grailed.com' in str(response.url):
                return str(response.url)
            
            html = await response.text()
            soup = BeautifulSoup(html, 'lxml')
            
            # Try meta refresh
            meta = soup.find('meta', attrs={'http-equiv': lambda v: v and v.lower() == 'refresh'})
            if meta and 'url=' in meta.get('content', ''):
                return meta['content'].split('url=', 1)[1]
            
            # Try direct link
            a = soup.find('a', href=re.compile(r'https?://(www\.)?grailed\.com/'))
            if a:
                return a['href']
                
    except Exception:
        pass
    
    return url


async def _scrape_ebay_item(url: str, session: aiohttp.ClientSession):
    """Scrape eBay item."""
    item_data = await ebay.get_item_data(url, session)
    return item_data, None


async def _scrape_grailed_item(url: str, session: aiohttp.ClientSession):
    """Scrape Grailed item."""
    return await grailed.get_item_data(url, session)


async def _return_none():
    """Return None for unsupported URLs."""
    return None