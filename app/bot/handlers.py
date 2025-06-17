"""Refactored Telegram bot handlers with clean architecture.

Simplified handlers that delegate to specialized components for
URL processing, scraping orchestration, response formatting,
and analytics tracking. Implements Single Responsibility Principle.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ..config import config
from ..services.analytics import analytics_service
from .analytics_tracker import analytics_tracker
from .feedback import is_waiting_feedback, handle_feedback_message
from .messages import START_MESSAGE, LOADING_MESSAGE, LOADING_SELLER_ANALYSIS
from .response_formatter import response_formatter
from .scraping_orchestrator import scraping_orchestrator
from .url_processor import url_processor
from .utils import safe_open_file

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
        
        # Log command usage
        if update.effective_user:
            analytics_tracker.log_command_usage(
                user_id=update.effective_user.id,
                username=update.effective_user.username,
                command='start'
            )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages containing marketplace URLs.

    Main handler that processes user messages containing eBay or Grailed URLs.
    Uses specialized components for URL processing, scraping, and response formatting.

    Args:
        update: Telegram update object containing message data.
        context: Bot context for accessing application instance.
    """
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    # Handle feedback messages first
    if is_waiting_feedback(user_id):
        await handle_feedback_message(update, context)
        return

    text = update.message.text if update.message else ''
    
    # Process URLs using specialized processor
    url_result = url_processor.process_message(text, user_id)
    
    if not url_result['valid_urls']:
        # Log suspicious activity if detected
        if url_result['has_suspicious']:
            raw_urls = url_processor.extract_urls(text)
            suspicious_urls = [url for url in raw_urls 
                             if url not in url_result['valid_urls']]
            analytics_tracker.log_suspicious_activity(
                user_id, username, suspicious_urls, text
            )
        return

    valid_urls = url_result['valid_urls']
    categorized = url_result['categorized']

    # Send loading message
    loading_msg = response_formatter.format_loading_message(valid_urls)
    loading_message = await update.message.reply_text(loading_msg)

    try:
        # Handle seller profiles first (priority)
        if categorized.get('seller_profiles'):
            profile_url = categorized['seller_profiles'][0]
            
            # Update loading message for seller analysis
            await loading_message.edit_text(LOADING_SELLER_ANALYSIS)
            
            # Process seller profile
            results = await scraping_orchestrator.process_urls_concurrent(
                [profile_url], user_id, username
            )
            
            if results:
                response = response_formatter.format_seller_profile_response(results[0])
                await loading_message.edit_text(response, parse_mode='Markdown')
            
            return

        # Handle item listings
        if categorized.get('item_listings'):
            results = await scraping_orchestrator.process_urls_concurrent(
                categorized['item_listings'], user_id, username
            )
            
            # Delete loading message
            await loading_message.delete()
            
            # Send responses for each item
            for result in results:
                response = await response_formatter.format_item_response(result)
                await update.message.reply_text(
                    response, 
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )

    except Exception as e:
        logger.error(f"Error processing URLs: {e}")
        await loading_message.edit_text(
            "❌ Произошла ошибка при обработке ссылки. Попробуйте позже."
        )


# === ANALYTICS COMMANDS ===

async def analytics_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_daily command for admin."""
    if not _check_admin_permissions(update):
        return
    
    try:
        stats = analytics_service.get_daily_stats(days=1)
        response = response_formatter.format_analytics_response(
            stats, "Статистика за сегодня"
        )
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error getting daily analytics: {e}")
        await update.message.reply_text("❌ Ошибка при получении статистики")


async def analytics_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_week command for admin."""
    if not _check_admin_permissions(update):
        return
    
    try:
        stats = analytics_service.get_daily_stats(days=7)
        response = response_formatter.format_analytics_response(
            stats, "Статистика за неделю"
        )
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error getting weekly analytics: {e}")
        await update.message.reply_text("❌ Ошибка при получении статистики")


async def analytics_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_user command for admin."""
    if not _check_admin_permissions(update):
        return
    
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("❌ Использование: /analytics_user <user_id>")
        return
    
    try:
        user_id = int(context.args[0])
        stats = analytics_service.get_user_stats(user_id, days=30)
        
        if not stats:
            await update.message.reply_text(f"❌ Данные для пользователя {user_id} не найдены")
            return
            
        response = response_formatter.format_analytics_response(
            stats, f"Статистика пользователя {user_id}"
        )
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат user_id")
    except Exception as e:
        logger.error(f"Error getting user analytics: {e}")
        await update.message.reply_text("❌ Ошибка при получении статистики")


async def analytics_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_errors command for admin."""
    if not _check_admin_permissions(update):
        return
    
    days = 7
    if context.args and len(context.args) == 1:
        try:
            days = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат количества дней")
            return
    
    try:
        error_stats = analytics_service.get_error_analysis(days)
        
        if not error_stats:
            await update.message.reply_text("❌ Данные об ошибках не найдены")
            return
            
        message = f"📊 **Анализ ошибок за {days} дней**\\n\\n"
        
        if 'common_errors' in error_stats:
            message += "**Частые ошибки:**\\n"
            for error in error_stats['common_errors'][:5]:
                message += f"• {error['error_type']}: {error['count']}\\n"
            message += "\\n"
            
        if 'platform_failure_rates' in error_stats:
            message += "**Процент ошибок по платформам:**\\n"
            for platform in error_stats['platform_failure_rates']:
                rate = platform['failure_rate'] * 100
                message += f"• {platform['platform']}: {rate:.1f}%\\n"
                
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error getting error analytics: {e}")
        await update.message.reply_text("❌ Ошибка при анализе ошибок")


async def analytics_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_export command for admin."""
    if not _check_admin_permissions(update):
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
            try:
                safe_path = safe_open_file(filename, 'rb')
                with open(safe_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=filename,
                        caption=f"📊 Экспорт аналитики за {days or 'все'} дней"
                    )
            except ValueError as e:
                logger.error(f"File path validation error: {e}")
                await update.message.reply_text("❌ Ошибка при обработке файла экспорта")
            
            # Delete temporary file
            os.remove(filename)
        else:
            await update.message.reply_text("❌ Ошибка при экспорте данных")
        
    except Exception as e:
        logger.error(f"Error exporting analytics: {e}")
        await update.message.reply_text("❌ Ошибка при экспорте данных")


async def analytics_download_db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analytics_download_db command for admin."""
    if not _check_admin_permissions(update):
        return
    
    try:
        db_path = analytics_service.db_path
        
        if not Path(db_path).exists():
            await update.message.reply_text("❌ База данных не найдена")
            return
        
        with open(db_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"analytics_database_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                caption="📊 SQLite база данных аналитики\\n\\nМожно открыть в DBeaver, DB Browser или другом SQLite клиенте"
            )
        
        logger.info(f"Admin {update.effective_user.id} downloaded analytics database")
        
    except Exception as e:
        logger.error(f"Failed to download database: {e}")
        await update.message.reply_text("❌ Ошибка при скачивании базы данных")


# === HELPER FUNCTIONS ===

def _check_admin_permissions(update: Update) -> bool:
    """Check if user has admin permissions.
    
    Args:
        update: Telegram update object.
        
    Returns:
        True if user is admin, False otherwise.
    """
    if not update.effective_user or not update.message:
        return False
    
    return update.effective_user.id == config.bot.admin_chat_id