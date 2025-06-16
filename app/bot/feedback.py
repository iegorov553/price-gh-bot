"""Feedback command handler for the Telegram bot.

Handles the /feedback command allowing users to send messages that are
automatically converted to GitHub issues for tracking and response.
"""

import logging
from typing import Set

from telegram import Update
from telegram.ext import ContextTypes

from ..services.github import GitHubService
from .messages import FEEDBACK_REQUEST_MESSAGE, FEEDBACK_SUCCESS_MESSAGE, FEEDBACK_ERROR_MESSAGE

logger = logging.getLogger(__name__)

# Set of user IDs waiting to send feedback
waiting_feedback: Set[int] = set()

# GitHub service instance
github_service = GitHubService()


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /feedback command to start feedback collection.

    Args:
        update: Telegram update object.
        context: Bot context.
    """
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    waiting_feedback.add(user_id)
    
    await update.message.reply_text(FEEDBACK_REQUEST_MESSAGE, disable_web_page_preview=True)
    logger.info(f"User {user_id} started feedback process")


async def handle_feedback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text message from user who sent /feedback command.

    Args:
        update: Telegram update object.
        context: Bot context.
    """
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    message_text = update.message.text

    if not message_text:
        return

    # Validate message length
    if len(message_text) < 5:
        await update.message.reply_text("Сообщение слишком короткое. Напишите хотя бы 5 символов.", disable_web_page_preview=True)
        return

    if len(message_text) > 1000:
        await update.message.reply_text("Сообщение слишком длинное. Максимум 1000 символов.", disable_web_page_preview=True)
        return

    # Remove user from waiting set
    waiting_feedback.discard(user_id)

    # Try to create GitHub issue
    success = await github_service.create_feedback_issue(
        message=message_text,
        username=update.effective_user.username,
        user_id=user_id
    )

    # Send response to user
    if success:
        await update.message.reply_text(FEEDBACK_SUCCESS_MESSAGE, disable_web_page_preview=True)
        logger.info(f"Successfully processed feedback from user {user_id}")
    else:
        await update.message.reply_text(FEEDBACK_ERROR_MESSAGE, disable_web_page_preview=True)
        logger.error(f"Failed to process feedback from user {user_id}")


def is_waiting_feedback(user_id: int) -> bool:
    """Check if user is waiting to send feedback.

    Args:
        user_id: Telegram user ID.

    Returns:
        bool: True if user is in feedback waiting state.
    """
    return user_id in waiting_feedback


def clear_feedback_state(user_id: int) -> None:
    """Clear feedback waiting state for user.

    Args:
        user_id: Telegram user ID.
    """
    waiting_feedback.discard(user_id)