"""Telegram bot message and command handlers.

Implements the main bot interaction logic including command processing, URL
detection and parsing, marketplace scraping orchestration, and response
formatting. Handles both price calculation workflows and seller analysis
features with proper error handling and admin notifications.
"""

import asyncio
import logging
import re
from datetime import datetime
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
from ..config import config
from ..models import SearchAnalytics, SellerData
from ..scrapers import ebay, grailed
from ..services import currency, reliability, shipping
from ..services.analytics import analytics_service
from .utils import (
    calculate_final_price,
    create_session,
    detect_platform,
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


async def analytics_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_daily command for admin.

    Shows daily usage statistics including searches, success rates, and platform breakdown.
    Only accessible to admin user.

    Args:
        update: Telegram update object containing message data.
        context: Bot context for accessing application instance.
    """
    if not update.effective_user or not update.message:
        return
    
    # Check admin permissions (using admin ID from config)
    from ..config import config
    if update.effective_user.id != config.bot.admin_chat_id:
        return
    
    try:
        stats = analytics_service.get_daily_stats(days=1)
        
        if not stats:
            await update.message.reply_text("❌ Не удалось получить статистику")
            return
        
        message = f"""📊 **Статистика за сегодня**

🔍 Всего поисков: {stats['total_searches']}
✅ Успешных: {stats['successful_searches']}
📈 Процент успеха: {stats['success_rate']:.1%}
⏱️ Среднее время обработки: {stats['avg_processing_time_ms']:.0f}мс

**Платформы:**"""
        
        for platform, count in stats['platforms'].items():
            message += f"\n• {platform}: {count}"
        
        await update.message.reply_text(message, disable_web_page_preview=True)
        
    except Exception as e:
        logger.error(f"Error getting daily analytics: {e}")
        await update.message.reply_text("❌ Ошибка при получении статистики")


async def analytics_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_week command for admin.

    Shows weekly usage statistics and trends.
    Only accessible to admin user.

    Args:
        update: Telegram update object containing message data.
        context: Bot context for accessing application instance.
    """
    if not update.effective_user or not update.message:
        return
    
    # Check admin permissions
    from ..config import config
    if update.effective_user.id != config.bot.admin_chat_id:
        return
    
    try:
        stats = analytics_service.get_daily_stats(days=7)
        popular_items = analytics_service.get_popular_items(limit=5, days=7)
        
        if not stats:
            await update.message.reply_text("❌ Не удалось получить статистику")
            return
        
        message = f"""📊 **Статистика за неделю**

🔍 Всего поисков: {stats['total_searches']}
✅ Успешных: {stats['successful_searches']}
📈 Процент успеха: {stats['success_rate']:.1%}
⏱️ Среднее время: {stats['avg_processing_time_ms']:.0f}мс

**Платформы:**"""
        
        for platform, count in stats['platforms'].items():
            message += f"\n• {platform}: {count}"
        
        if popular_items:
            message += "\n\n**🔥 Популярные товары:**"
            for item in popular_items:
                title = item['item_title'][:50] + "..." if len(item['item_title']) > 50 else item['item_title']
                message += f"\n• {title} ({item['search_count']}x)"
        
        await update.message.reply_text(message, disable_web_page_preview=True)
        
    except Exception as e:
        logger.error(f"Error getting weekly analytics: {e}")
        await update.message.reply_text("❌ Ошибка при получении статистики")


async def analytics_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_user command for admin.

    Shows statistics for a specific user ID.
    Usage: /analytics_user <user_id>
    Only accessible to admin user.

    Args:
        update: Telegram update object containing message data.
        context: Bot context for accessing application instance.
    """
    if not update.effective_user or not update.message:
        return
    
    # Check admin permissions
    from ..config import config
    if update.effective_user.id != config.bot.admin_chat_id:
        return
    
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Использование: /analytics_user <user_id>")
        return
    
    try:
        user_id = int(context.args[0])
        stats = analytics_service.get_user_stats(user_id)
        
        if stats['total_searches'] == 0:
            await update.message.reply_text(f"👤 Пользователь {user_id}: данных нет")
            return
        
        message = f"""👤 **Статистика пользователя {user_id}**

👋 Username: @{stats.get('username', 'не указан')}
🔍 Всего поисков: {stats['total_searches']}
✅ Успешных: {stats['successful_searches']}
📈 Процент успеха: {stats['success_rate']:.1%}
💰 Средняя цена: ${stats['avg_price_usd']:.2f}

**Платформы:**"""
        
        for platform, count in stats['platforms'].items():
            message += f"\n• {platform}: {count}"
        
        message += f"\n\n📅 Первый поиск: {stats['first_search']}"
        message += f"\n📅 Последний поиск: {stats['last_search']}"
        
        await update.message.reply_text(message, disable_web_page_preview=True)
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат user_id")
    except Exception as e:
        logger.error(f"Error getting user analytics: {e}")
        await update.message.reply_text("❌ Ошибка при получении статистики")


async def analytics_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_errors command for admin.

    Shows error analysis and failure patterns.
    Only accessible to admin user.

    Args:
        update: Telegram update object containing message data.
        context: Bot context for accessing application instance.
    """
    if not update.effective_user or not update.message:
        return
    
    # Check admin permissions
    from ..config import config
    if update.effective_user.id != config.bot.admin_chat_id:
        return
    
    try:
        error_analysis = analytics_service.get_error_analysis(days=7)
        
        if not error_analysis:
            await update.message.reply_text("❌ Не удалось получить анализ ошибок")
            return
        
        message = "🚨 **Анализ ошибок за неделю**\n\n"
        
        if error_analysis.get('common_errors'):
            message += "**Частые ошибки:**\n"
            for error in error_analysis['common_errors'][:5]:
                message += f"• {error['error_message'][:50]}... ({error['count']}x)\n"
        
        if error_analysis.get('platform_failure_rates'):
            message += "\n**Процент ошибок по платформам:**\n"
            for platform in error_analysis['platform_failure_rates']:
                rate = platform['failure_rate'] * 100
                message += f"• {platform['platform']}: {rate:.1f}% ({platform['failures']}/{platform['total']})\n"
        
        await update.message.reply_text(message, disable_web_page_preview=True)
        
    except Exception as e:
        logger.error(f"Error getting error analytics: {e}")
        await update.message.reply_text("❌ Ошибка при получении анализа ошибок")


async def analytics_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_export command for admin.

    Exports analytics data to CSV and sends as document.
    Usage: /analytics_export [days]
    Only accessible to admin user.

    Args:
        update: Telegram update object containing message data.
        context: Bot context for accessing application instance.
    """
    if not update.effective_user or not update.message:
        return
    
    # Check admin permissions
    from ..config import config
    if update.effective_user.id != config.bot.admin_chat_id:
        return
    
    days = None
    if context.args and len(context.args) == 1:
        try:
            days = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат количества дней")
            return
    
    try:
        filename = f"analytics_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        success = analytics_service.export_to_csv(filename, days)
        
        if success:
            with open(filename, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📊 Экспорт аналитики за {days or 'все'} дней"
                )
            
            # Delete temporary file
            import os
            os.remove(filename)
        else:
            await update.message.reply_text("❌ Ошибка при экспорте данных")
        
    except Exception as e:
        logger.error(f"Error exporting analytics: {e}")
        await update.message.reply_text("❌ Ошибка при экспорте данных")


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
    if not update.message or not update.effective_user:
        return
        
    loading_message = await update.message.reply_text(LOADING_SELLER_ANALYSIS)
    start_time = datetime.now()
    
    # Prepare analytics data
    user_id = update.effective_user.id
    username = update.effective_user.username

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

            # Log successful analytics
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            analytics_data = SearchAnalytics(
                url=profile_url,
                user_id=user_id,
                username=username,
                platform="profile",
                success=True,
                seller_score=reliability_score.total_score,
                seller_category=reliability_score.category,
                processing_time_ms=processing_time
            )
            analytics_service.log_search(analytics_data)

            # Delete loading message and send final response
            await loading_message.delete()
            await update.message.reply_text(response, disable_web_page_preview=True)
        else:
            # Log failed analytics
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            analytics_data = SearchAnalytics(
                url=profile_url,
                user_id=user_id,
                username=username,
                platform="profile",
                success=False,
                error_message="Seller data not found",
                processing_time_ms=processing_time
            )
            analytics_service.log_search(analytics_data)
            
            await loading_message.delete()
            await update.message.reply_text(ERROR_SELLER_DATA_NOT_FOUND, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error processing seller profile {profile_url}: {e}")
        
        # Log error analytics
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        analytics_data = SearchAnalytics(
            url=profile_url,
            user_id=user_id,
            username=username,
            platform="profile",
            success=False,
            error_message=str(e),
            processing_time_ms=processing_time
        )
        analytics_service.log_search(analytics_data)
        
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
    if not update.message or not update.effective_user:
        return
    loading_message = await update.message.reply_text(LOADING_MESSAGE)
    start_time = datetime.now()
    
    # Prepare analytics data
    user_id = update.effective_user.id
    username = update.effective_user.username

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
            # Log failed analytics for price not found
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            analytics_data = SearchAnalytics(
                url=url,
                user_id=user_id,
                username=username,
                platform=detect_platform(url),
                success=False,
                error_message="Price not found",
                item_title=item_data.title,
                processing_time_ms=processing_time
            )
            analytics_service.log_search(analytics_data)
            
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
                except Exception as e:
                    logger.warning(f"Failed to send offer-only photo for {url}: {e}")
                    # Fallback to text message
                    await update.message.reply_text(offer_message)
            else:
                # Send text message
                await update.message.reply_text(offer_message)
            
            # Log analytics for offer-only items (still successful)
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            analytics_data = SearchAnalytics(
                url=url,
                user_id=user_id,
                username=username,
                platform=detect_platform(url),
                success=True,
                item_price=item_data.price,
                shipping_us=item_data.shipping_us,
                item_title=item_data.title,
                is_buyable=item_data.is_buyable,
                processing_time_ms=processing_time
            )
            analytics_service.log_search(analytics_data)
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
        
        # Log successful analytics for processed listing
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        analytics_data = SearchAnalytics(
            url=url,
            user_id=user_id,
            username=username,
            platform=detect_platform(url),
            success=True,
            item_price=item_data.price,
            shipping_us=item_data.shipping_us,
            item_title=item_data.title,
            seller_score=reliability_score.total_score if reliability_score else None,
            seller_category=reliability_score.category if reliability_score else None,
            final_price_usd=calculation.final_price_usd,
            commission=calculation.commission,
            is_buyable=item_data.is_buyable,
            processing_time_ms=processing_time
        )
        analytics_service.log_search(analytics_data)


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
