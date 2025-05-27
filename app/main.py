"""Application entry point.

Main module that initializes and runs the Telegram bot application. Handles both
webhook mode (for production deployment on Railway) and polling mode (for local
development). Configures logging and registers bot handlers for commands and
message processing.
"""

import logging
import os

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .bot.handlers import start, handle_link
from .config import config

# Logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", 
    level=logging.DEBUG  # Enable debug logging
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Main application entry point.
    
    Initializes the Telegram bot application with proper configuration,
    registers command and message handlers, and starts the bot in either
    webhook mode (production) or polling mode (development).
    
    Raises:
        RuntimeError: If BOT_TOKEN environment variable is not set.
    """
    if not config.bot.bot_token:
        raise RuntimeError('Set BOT_TOKEN environment variable')
    
    # Create application
    app = Application.builder().token(config.bot.bot_token).build()
    
    # Add handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    # Run in webhook or polling mode
    if config.bot.use_webhook:
        path = f"/{config.bot.bot_token}"
        webhook_url = f"https://{config.bot.webhook_domain}{path}"
        logger.info(f"Starting webhook at {webhook_url}")
        
        app.run_webhook(
            listen='0.0.0.0',
            port=config.bot.port,
            url_path=path,
            webhook_url=webhook_url,
        )
    else:
        logger.warning('No public domain found; falling back to long-polling')
        app.run_polling()


if __name__ == '__main__':
    main()