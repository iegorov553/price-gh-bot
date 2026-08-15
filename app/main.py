"""Application entry point.

Main module that initializes and runs the Telegram bot application. Handles both
webhook mode (for production deployment on Railway) and polling mode (for local
development). Configures logging and registers bot handlers for commands and
message processing.
"""

import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .bot.feedback import feedback_command
from .bot.handlers import (
    analytics_daily,
    analytics_download_db,
    analytics_errors,
    analytics_export,
    analytics_user,
    analytics_week,
    handle_link,
    start,
)
from .config import config
from .logging_config import configure_logging

configure_logging(config.bot.log_level)
logger = logging.getLogger(__name__)


async def initialize_resources() -> None:
    """Initialize application resources."""
    if config.bot.enable_headless_browser:
        try:
            from .scrapers.headless import get_global_browser

            await get_global_browser()
            logger.info("Chromium scraper browser initialized")
        except Exception as exc:
            logger.warning("Failed to initialize Chromium scraper browser: %s", exc)

    try:
        from .services.cache_service import get_cache_service

        cache = await get_cache_service()
        if cache._connected:
            logger.info("Redis кэш подключен")
        else:
            logger.info("Redis кэш недоступен, работаем без кэширования")

    except Exception as exc:
        logger.warning("Failed to initialize cache service: %s", exc)


async def cleanup_resources() -> None:
    """Cleanup application resources."""
    try:
        # Закрываем cache service
        from .services.cache_service import shutdown_cache_service

        await shutdown_cache_service()
        logger.info("Cache service закрыт")

        from .scrapers.headless import cleanup_global_browser

        await cleanup_global_browser()
        logger.info("Chromium scraper browser closed")

    except Exception as e:
        logger.warning(f"Error during cleanup: {e}")


def main() -> None:
    """Main application entry point.

    Initializes the Telegram bot application with proper configuration,
    registers command and message handlers, and starts the bot in either
    webhook mode (production) or polling mode (development).

    Raises:
        RuntimeError: If BOT_TOKEN environment variable is not set.
    """
    if not config.bot.bot_token:
        raise RuntimeError("Set BOT_TOKEN environment variable")

    # Create application
    app = Application.builder().token(config.bot.bot_token).build()

    # Initialize the single shared Chromium instance on startup
    async def post_init(application: Application) -> None:
        await initialize_resources()

    async def post_shutdown(application: Application) -> None:
        await cleanup_resources()

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("feedback", feedback_command))

    # Analytics commands for admin
    app.add_handler(CommandHandler("analytics_daily", analytics_daily))
    app.add_handler(CommandHandler("analytics_week", analytics_week))
    app.add_handler(CommandHandler("analytics_user", analytics_user))
    app.add_handler(CommandHandler("analytics_errors", analytics_errors))
    app.add_handler(CommandHandler("analytics_export", analytics_export))
    app.add_handler(CommandHandler("analytics_download_db", analytics_download_db))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    # Run in webhook or polling mode
    if config.bot.use_webhook:
        path = f"/{config.bot.bot_token}"
        webhook_url = f"https://{config.bot.webhook_domain}{path}"
        logger.info("Starting webhook for domain %s", config.bot.webhook_domain)

        listen_host = config.bot.listen_host
        app.run_webhook(
            listen=listen_host,
            port=config.bot.port,
            url_path=path,
            webhook_url=webhook_url,
        )
    else:
        logger.warning("No public domain found; falling back to long-polling")
        app.run_polling()


if __name__ == "__main__":
    main()
