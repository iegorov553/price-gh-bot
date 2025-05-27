"""Application entry point."""

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
    """Main application entry point."""
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