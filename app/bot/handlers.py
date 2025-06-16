"""Telegram bot message and command handlers.

Implements the main bot interaction logic including command processing, URL
detection and parsing, marketplace scraping orchestration, and response
formatting. Handles both price calculation workflows and seller analysis
features with proper error handling and admin notifications.
"""

import asyncio
import logging
import re
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes

from ..bot.messages import (
    ERROR_PRICE_NOT_FOUND,
    ERROR_SELLER_ANALYSIS,
    ERROR_SELLER_DATA_NOT_FOUND,
    GRAILED_LISTING_ISSUE,
    GRAILED_SITE_DOWN,
    GRAILED_SITE_SLOW,
    LOADING_MESSAGE,
    LOADING_SELLER_ANALYSIS,
    LOG_CBR_API_FAILED,
    OFFER_ONLY_MESSAGE,
    START_MESSAGE,
)
from ..models import SellerData
from ..scrapers import ebay, grailed
from ..services import currency, reliability, shipping
from .utils import (
    calculate_final_price,
    create_session,
    format_price_response,
    format_seller_profile_response,
    notify_admin,
    send_debug_to_admin,
)

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command.

    Sends welcome message with bot usage instructions and pricing information.

    Args:
        update: Telegram update object containing message data.
        context: Bot context for accessing application instance.
    """
    if update.message:
        await update.message.reply_text(START_MESSAGE, disable_web_page_preview=True)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages containing marketplace URLs.

    Main handler that processes user messages containing eBay or Grailed URLs.
    Detects seller profile links vs item listings and routes to appropriate
    processing workflow. Handles concurrent scraping and response formatting.
    Also handles feedback messages from users in feedback mode.

    Args:
        update: Telegram update object containing message data.
        context: Bot context for accessing application instance.
    """
    if not update.message or not update.effective_user:
        return

    # Check if user is waiting to send feedback
    from .feedback import is_waiting_feedback, handle_feedback_message
    
    user_id = update.effective_user.id
    if is_waiting_feedback(user_id):
        await handle_feedback_message(update, context)
        return

    text = update.message.text if update.message else ''
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
    """Handle Grailed seller profile analysis.

    Analyzes a Grailed seller profile URL and sends reliability evaluation.

    Args:
        update: Telegram update object containing message data.
        context: Bot context for accessing application instance.
        profile_url: Grailed seller profile URL to analyze.
        session: HTTP session for making requests.
    """
    # Send loading message
    if not update.message:
        return
    loading_message = await update.message.reply_text(LOADING_SELLER_ANALYSIS)

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

            # Delete loading message and send final response
            await loading_message.delete()
            await update.message.reply_text(response, disable_web_page_preview=True)
        else:
            await loading_message.delete()
            await update.message.reply_text(ERROR_SELLER_DATA_NOT_FOUND, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error processing seller profile {profile_url}: {e}")
        await loading_message.delete()
        await update.message.reply_text(ERROR_SELLER_ANALYSIS, disable_web_page_preview=True)
        await send_debug_to_admin(context.application, f"Seller profile error for {profile_url}: {e}")


async def _handle_listings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    urls: list,
    session: aiohttp.ClientSession
) -> None:
    """Handle regular marketplace listings.

    Processes marketplace item URLs, calculates prices with shipping and fees,
    and sends formatted responses with optional seller reliability analysis.

    Args:
        update: Telegram update object containing message data.
        context: Bot context for accessing application instance.
        urls: List of marketplace URLs to process.
        session: HTTP session for making requests.
    """
    # Send loading message
    if not update.message:
        return
    loading_message = await update.message.reply_text(LOADING_MESSAGE)

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

    # Check if we have any valid results
    has_valid_results = any(result is not None for result in results)

    # Delete loading message before sending results
    await loading_message.delete()

    # If no valid results, nothing to process
    if not has_valid_results:
        return

    # Process results
    for url, result in zip(resolved_urls, results, strict=False):
        if result is None:
            continue

        item_data, seller_data = result

        if not item_data.price:
            # Enhanced error handling with site availability check for Grailed
            if grailed.is_grailed_url(url):
                await _handle_grailed_scraping_failure(update, session)
            else:
                await update.message.reply_text(ERROR_PRICE_NOT_FOUND, disable_web_page_preview=True)
            continue

        if not item_data.is_buyable:
            # For offer-only items
            offer_message = OFFER_ONLY_MESSAGE.format(price=item_data.price)
            
            # Try to send with photo if available
            if item_data.image_url:
                try:
                    await update.message.reply_photo(
                        photo=item_data.image_url,
                        caption=offer_message
                    )
                    continue
                except Exception as e:
                    logger.warning(f"Failed to send offer-only photo for {url}: {e}")
            
            # Fallback to text message
            await update.message.reply_text(offer_message)
            continue

        # Calculate shipping and final price
        total_order_value = item_data.price + (item_data.shipping_us or 0)
        shopfans_quote = shipping.estimate_shopfans_shipping(item_data.title or "", total_order_value)
        calculation = await calculate_final_price(
            item_data.price,
            item_data.shipping_us or 0,
            shopfans_quote.cost_usd,
            session
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
        use_markdown = bool(item_data.title and url)
        response = format_price_response(
            calculation,
            exchange_rate,
            reliability_score,
            is_grailed_item,
            item_data.title,
            url,
            use_markdown
        )

        # Try to send as photo with caption if image is available
        if item_data.image_url:
            try:
                parse_mode = "MarkdownV2" if use_markdown else None
                await update.message.reply_photo(
                    photo=item_data.image_url,
                    caption=response,
                    parse_mode=parse_mode
                )
                continue  # Successfully sent photo, continue to next item
            except Exception as e:
                logger.warning(f"Failed to send photo for {url}: {e}")
                # Fallback to text message

        # Send as text message (fallback or when no image)
        parse_mode = "MarkdownV2" if use_markdown else None
        await update.message.reply_text(
            response, 
            parse_mode=parse_mode, 
            disable_web_page_preview=True
        )


async def _resolve_shortener(url: str, session: aiohttp.ClientSession) -> str:
    """Resolve Grailed app.link shorteners.

    Follows redirects from Grailed app.link URLs to get final destination.

    Args:
        url: URL to resolve, potentially a shortener.
        session: HTTP session for making requests.

    Returns:
        Resolved URL or original URL if not a shortener.
    """
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
    """Scrape eBay item data.

    Extracts item information from eBay listing page.

    Args:
        url: eBay item URL to scrape.
        session: HTTP session for making requests.

    Returns:
        Tuple of (item_data, None) since eBay doesn't provide seller data.
    """
    item_data = await ebay.get_item_data(url, session)
    return item_data, None


async def _scrape_grailed_item(url: str, session: aiohttp.ClientSession):
    """Scrape Grailed item data.

    Extracts item and seller information from Grailed listing page.

    Args:
        url: Grailed item URL to scrape.
        session: HTTP session for making requests.

    Returns:
        Tuple of (item_data, seller_data) from the listing.
    """
    return await grailed.get_item_data(url, session)


async def _return_none():
    """Return None for unsupported URLs.

    Helper function used in asyncio.gather for non-marketplace URLs.

    Returns:
        None to indicate no data extracted.
    """
    return None


async def _handle_grailed_scraping_failure(
    update: Update,
    session: aiohttp.ClientSession
) -> None:
    """Handle Grailed scraping failure with enhanced diagnostics.

    When Grailed listing scraping fails, this function checks if the entire
    Grailed website is accessible to provide more helpful error messages to users.

    Args:
        update: Telegram update object containing message data.
        session: HTTP session for making requests.
    """
    logger.info("Checking Grailed availability after scraping failure")

    try:
        # Check if Grailed site is available
        availability = await grailed.check_grailed_availability(session)

        if not availability['is_available']:
            status_code = availability.get('status_code', 'неизвестно')
            response_time = availability.get('response_time_ms', 0)

            if availability.get('error_message') and 'timeout' in availability['error_message'].lower():
                # Site is slow or timing out
                message = GRAILED_SITE_SLOW.format(response_time=response_time)
            else:
                # Site is down or returning errors
                message = GRAILED_SITE_DOWN.format(
                    status_code=status_code,
                    response_time=response_time
                )

            await update.message.reply_text(message, disable_web_page_preview=True)
            logger.warning(f"Grailed site availability issue: {availability}")

        else:
            # Site is working, likely issue with specific listing
            await update.message.reply_text(GRAILED_LISTING_ISSUE, disable_web_page_preview=True)
            logger.info("Grailed site is accessible, likely listing-specific issue")

    except Exception as e:
        # Fallback to generic error if availability check fails
        logger.error(f"Error during Grailed availability check: {e}")
        await update.message.reply_text(ERROR_PRICE_NOT_FOUND, disable_web_page_preview=True)
