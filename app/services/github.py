"""GitHub API service for creating issues from user feedback.

Simple service to create GitHub issues when users send feedback through the bot.
Handles authentication and basic issue creation without complex features.
"""

import logging
from datetime import datetime, UTC

import aiohttp

from ..config import config

logger = logging.getLogger(__name__)


class GitHubService:
    """Simple GitHub API client for creating issues."""

    def __init__(self):
        """Initialize GitHub service with configuration."""
        self.token = config.bot.github_token
        self.owner = config.bot.github_owner
        self.repo = config.bot.github_repo
        self.base_url = "https://api.github.com"

    async def create_feedback_issue(
        self,
        message: str,
        username: str | None = None,
        user_id: int | None = None
    ) -> bool:
        """Create a GitHub issue from user feedback.

        Args:
            message: User's feedback message content.
            username: Telegram username (without @).
            user_id: Telegram user ID.

        Returns:
            bool: True if issue was created successfully, False otherwise.
        """
        if not self.token:
            logger.warning("GitHub token not configured, skipping issue creation")
            return False

        # Create issue title from first 50 characters
        title_text = message[:50].strip()
        if len(message) > 50:
            title_text += "..."
        title = f"[Feedback] {title_text}"

        # Create issue body
        body_lines = [
            f"**От:** @{username or 'unknown'} (ID: {user_id or 'unknown'})",
            f"**Дата:** {datetime.now(UTC).strftime('%d.%m.%Y %H:%M')}",
            "",
            "**Сообщение:**",
            message
        ]
        body = "\n".join(body_lines)

        # Create issue payload
        payload = {
            "title": title,
            "body": body
        }

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"token {self.token}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "PriceBot-Feedback/1.0"
                }

                url = f"{self.base_url}/repos/{self.owner}/{self.repo}/issues"
                
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 201:
                        data = await response.json()
                        issue_number = data.get("number")
                        logger.info(f"Created GitHub issue #{issue_number} for user {user_id}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create GitHub issue: {response.status} - {error_text}")
                        return False

        except Exception as e:
            logger.error(f"Error creating GitHub issue: {e}")
            return False