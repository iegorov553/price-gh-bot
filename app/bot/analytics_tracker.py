"""Analytics tracking and logging for bot interactions.

Handles comprehensive analytics logging including user behavior,
performance metrics, error tracking, and business intelligence data.
"""

import logging
from datetime import datetime
from typing import Any

from ..models import SearchAnalytics
from ..services.analytics import AnalyticsService, analytics_service

logger = logging.getLogger(__name__)


class AnalyticsTracker:
    """Tracks and logs analytics data for bot interactions.

    Responsibilities:
    - Log user search behavior and patterns
    - Track performance metrics and processing times
    - Monitor error rates and types
    - Collect business intelligence data
    - Provide analytics aggregation and reporting
    """

    def __init__(self, analytics_service: "AnalyticsService"):
        """Initialize analytics tracker."""
        self.analytics_service = analytics_service
        self.enabled = True

    def log_url_processing(
        self,
        user_id: int,
        username: str | None,
        url: str,
        platform: str,
        success: bool,
        processing_time_ms: int,
        error_type: str | None = None,
        item_data: Any | None = None,
        seller_data: Any | None = None,
        final_price_rub: float | None = None,
    ) -> None:
        """Log URL processing event to analytics.

        Args:
            user_id: User ID who made the request.
            username: Username (if available).
            url: Processed URL.
            platform: Platform name (ebay, grailed, etc.).
            success: Whether processing was successful.
            processing_time_ms: Processing time in milliseconds.
            error_type: Error description if failed.
            item_data: Item data object if available.
            seller_data: Seller data object if available.
            final_price_rub: Final calculated price in RUB.
        """
        if not self.enabled:
            return

        try:
            analytics_data = SearchAnalytics(
                user_id=user_id,
                username=username,
                timestamp=datetime.now(),
                url=url,
                platform=platform,
                success=success,
                processing_time_ms=processing_time_ms,
                error_message=error_type,
                item_title=getattr(item_data, "title", None),
                item_price=getattr(item_data, "price", None),
                shipping_us=getattr(item_data, "shipping_us", None),
                is_buyable=getattr(item_data, "is_buyable", None),
                final_price_usd=None,
                commission=None,
                seller_score=None,
                seller_category=None,
            )

            self.analytics_service.log_search(analytics_data)
            logger.debug(f"Logged analytics for user {user_id}: {platform} - {success}")

        except Exception as e:
            logger.error(f"Failed to log analytics: {e}")

    def log_seller_analysis(
        self,
        user_id: int,
        username: str | None,
        url: str,
        success: bool,
        processing_time_ms: int,
        seller_data: Any | None = None,
        seller_advisory: Any | None = None,
        error_type: str | None = None,
    ) -> None:
        """Log seller profile analysis event.

        Args:
            user_id: User ID who made the request.
            username: Username (if available).
            url: Seller profile URL.
            success: Whether analysis was successful.
            processing_time_ms: Processing time in milliseconds.
            seller_data: Seller data object if available.
            seller_advisory: Advisory object with recommendation (if calculated).
            error_type: Error description if failed.
        """
        if not self.enabled:
            return

        try:
            analytics_data = SearchAnalytics(
                user_id=user_id,
                username=username,
                timestamp=datetime.now(),
                url=url,
                platform="grailed",  # Only Grailed has seller profiles
                success=success,
                processing_time_ms=processing_time_ms,
                error_message=error_type,
                item_title=None,
                item_price=None,
                shipping_us=None,
                is_buyable=None,
                final_price_usd=None,
                commission=None,
                seller_score=None,
                seller_category=None,
                seller_warning_reason=getattr(seller_advisory, "reason", None),
                seller_warning_message=getattr(seller_advisory, "message", None),
            )

            self.analytics_service.log_search(analytics_data)
            logger.debug(f"Logged seller analysis for user {user_id}: {success}")

        except Exception as e:
            logger.error(f"Failed to log seller analytics: {e}")

    def log_command_usage(
        self,
        user_id: int,
        username: str | None,
        command: str,
        success: bool = True,
        processing_time_ms: int = 0,
    ) -> None:
        """Log bot command usage.

        Args:
            user_id: User ID who used the command.
            username: Username (if available).
            command: Command name (start, feedback, analytics_*).
            success: Whether command executed successfully.
            processing_time_ms: Processing time in milliseconds.
        """
        if not self.enabled:
            return

        try:
            analytics_data = SearchAnalytics(
                user_id=user_id,
                username=username,
                timestamp=datetime.now(),
                url=f"command://{command}",
                platform="telegram_bot",
                success=success,
                processing_time_ms=processing_time_ms,
                # Mark as command for filtering
                item_title=f"Command: {command}",
            )

            self.analytics_service.log_search(analytics_data)
            logger.debug(f"Logged command usage: {command} by user {user_id}")

        except Exception as e:
            logger.error(f"Failed to log command analytics: {e}")

    def log_suspicious_activity(
        self, user_id: int, username: str | None, suspicious_urls: list[str], message_text: str
    ) -> None:
        """Log suspicious user activity for security monitoring.

        Args:
            user_id: User ID who sent suspicious content.
            username: Username (if available).
            suspicious_urls: List of suspicious URLs.
            message_text: Original message text.
        """
        if not self.enabled:
            return

        try:
            # Log each suspicious URL separately
            for url in suspicious_urls:
                analytics_data = SearchAnalytics(
                    user_id=user_id,
                    username=username,
                    timestamp=datetime.now(),
                    url=url,
                    platform="suspicious",
                    success=False,
                    processing_time_ms=0,
                    error_message="security_filtered",
                    # Store message context
                    item_title=f"Suspicious: {message_text[:100]}",
                )

                analytics_service.log_search(analytics_data)

            logger.warning(
                f"Logged suspicious activity from user {user_id}: "
                f"{len(suspicious_urls)} filtered URLs"
            )

        except Exception as e:
            logger.error(f"Failed to log suspicious activity: {e}")

    def get_user_stats(self, user_id: int, days: int = 30) -> dict[str, Any]:
        """Get analytics statistics for specific user.

        Args:
            user_id: User ID to analyze.
            days: Number of days to look back.

        Returns:
            Dictionary with user statistics.
        """
        try:
            return self.analytics_service.get_user_stats(user_id, days=days)
        except Exception as e:
            logger.error(f"Failed to get user stats: {e}")
            return {}

    def get_platform_stats(self, days: int = 7) -> dict[str, Any]:
        """Get platform usage statistics.

        Args:
            days: Number of days to analyze.

        Returns:
            Dictionary with platform statistics.
        """
        try:
            return self.analytics_service.get_daily_stats(days)
        except Exception as e:
            logger.error(f"Failed to get platform stats: {e}")
            return {}

    def disable_tracking(self) -> None:
        """Disable analytics tracking (for testing/privacy)."""
        self.enabled = False
        logger.info("Analytics tracking disabled")

    def enable_tracking(self) -> None:
        """Enable analytics tracking."""
        self.enabled = True
        logger.info("Analytics tracking enabled")


analytics_tracker = AnalyticsTracker(analytics_service)
