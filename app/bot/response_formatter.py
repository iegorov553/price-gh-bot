"""Response formatting for bot messages and user interactions.

Handles formatting of price calculations, seller analysis, error messages,
and other user-facing content with proper localization and structure.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..services.currency import get_optimized_currency_service
from ..services.seller_assessment import evaluate_seller_advisory
from .messages import (
    CALCULATION_TIMESTAMP_FORMAT,
    CALCULATION_TIMESTAMP_LINE,
    ERROR_PRICE_NOT_FOUND,
    ERROR_SELLER_ANALYSIS,
    ERROR_SELLER_DATA_NOT_FOUND,
    GRAILED_LISTING_ISSUE,
    GRAILED_SITE_DOWN,
    GRAILED_SITE_SLOW,
    NEGOTIATION_NOTE_LINE,
    SELLER_OK_MESSAGE,
)
from .types import BaseScrapeResult
from .utils import (
    calculate_final_price_from_item,
    format_price_response,
)

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """Formats bot responses for pricing, seller advisories, and errors."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        """Initialize response formatter with optional clock provider."""
        self._clock = clock or (lambda: datetime.now().astimezone())

    async def format_item_response(self, scraping_result: BaseScrapeResult) -> str:
        """Format response for item listing analysis.

        Args:
            scraping_result: Result from scraping orchestrator.

        Returns:
            Formatted message string for user.
        """
        if not scraping_result["success"]:
            return self._format_error_response(scraping_result)

        item_data = scraping_result["item_data"]
        seller_data = scraping_result.get("seller_data")

        if not item_data:
            return ERROR_PRICE_NOT_FOUND

        # Формируем предупреждение до расчётов
        advisory = evaluate_seller_advisory(seller_data=seller_data, item_data=item_data)
        warning_message: str | None = advisory.message

        # Calculate final price
        try:
            price_calculation = await calculate_final_price_from_item(item_data)

            # Get USD to RUB exchange rate (оптимизированная версия)
            exchange_rate = None
            try:
                # Use a temporary session for currency
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    currency_service = await get_optimized_currency_service()
                    exchange_rate = await currency_service.get_usd_to_rub_rate_optimized(session)
            except Exception as e:
                logger.warning(f"Failed to get exchange rate: {e}")

            # Format main price response
            response = format_price_response(
                calculation=price_calculation,
                exchange_rate=exchange_rate,
                item_title=item_data.title,
                item_url=scraping_result.get("url"),
                use_markdown=False,
            )

            if warning_message:
                response = "\n".join([response, "", warning_message])

            response = "\n".join(
                [
                    response,
                    "",
                    NEGOTIATION_NOTE_LINE,
                    "",
                    self._format_calculation_timestamp_line(),
                ]
            )

            return response

        except Exception as e:
            logger.error(f"Failed to calculate price: {e}")
            return ERROR_PRICE_NOT_FOUND

    def format_seller_profile_response(self, scraping_result: BaseScrapeResult) -> str:
        """Format response for seller profile analysis.

        Args:
            scraping_result: Result from scraping orchestrator.

        Returns:
            Formatted seller analysis message.
        """
        if not scraping_result["success"]:
            return self._format_seller_error_response(scraping_result)

        seller_data = scraping_result["seller_data"]
        if not seller_data:
            return ERROR_SELLER_DATA_NOT_FOUND

        advisory = scraping_result.get("seller_advisory")
        if advisory is None:
            advisory = evaluate_seller_advisory(seller_data=seller_data)
        if advisory.message:
            return advisory.message

        return SELLER_OK_MESSAGE

    async def format_multiple_urls_response(
        self,
        results: list[BaseScrapeResult],
    ) -> list[str]:
        """Format responses for multiple URL processing.

        Args:
            results: List of scraping results.

        Returns:
            List of formatted response messages.
        """
        responses: list[str] = []

        for result in results:
            platform = result["platform"]

            if platform == "profile":
                response = self.format_seller_profile_response(result)
            else:
                response = await self.format_item_response(result)

            responses.append(response)

        return responses

    def _format_error_response(self, result: BaseScrapeResult) -> str:
        """Format error response based on platform and error type.

        Args:
            result: Scraping result with error.

        Returns:
            Formatted error message.
        """
        platform = result["platform"]
        error = result.get("error") or "Unknown error"
        error_lower = error.lower()

        # Grailed-specific error handling
        if platform == "grailed":
            if "timeout" in error_lower or "slow" in error_lower:
                return GRAILED_SITE_SLOW
            elif (
                "connection" in error_lower
                or "unavailable" in error_lower
                or " 500" in error_lower
                or " 503" in error_lower
                or "server error" in error_lower
            ):
                return GRAILED_SITE_DOWN
            elif "listing" in error_lower:
                return GRAILED_LISTING_ISSUE

        # Generic error message
        logger.error(f"Scraping error for {platform}: {error}")
        return ERROR_PRICE_NOT_FOUND

    def _format_seller_error_response(self, result: BaseScrapeResult) -> str:
        """Format seller analysis error response.

        Args:
            result: Scraping result with error.

        Returns:
            Formatted error message.
        """
        error = result.get("error") or "Unknown error"

        if "headless" in error.lower() or "browser" in error.lower():
            return (
                "❌ Анализ продавца временно недоступен\n"
                "Попробуйте позже или используйте ссылку на товар"
            )

        logger.error(f"Seller analysis error: {error}")
        return ERROR_SELLER_ANALYSIS

    def format_loading_message(self, urls: list[str]) -> str:
        """Format loading message for URL processing.

        Args:
            urls: List of URLs being processed.

        Returns:
            Loading message string.
        """
        if len(urls) == 1:
            return "⏳ Загружаем данные и производим расчёт..."
        else:
            return f"⏳ Обрабатываем {len(urls)} ссылок..."

    def format_analytics_response(
        self,
        stats: dict[str, Any],
        title: str,
    ) -> str:
        """Format analytics statistics response.

        Args:
            stats: Statistics dictionary.
            title: Response title.

        Returns:
            Formatted analytics message.
        """
        if not stats:
            return "❌ Не удалось получить статистику"

        message = f"📊 **{title}**\n\n"
        message += f"🔍 Всего поисков: {stats['total_searches']}\n"
        message += f"✅ Успешных: {stats['successful_searches']}\n"
        message += f"📈 Процент успеха: {stats['success_rate']:.1%}\n"
        message += f"⏱️ Среднее время: {stats['avg_processing_time_ms']:.0f}мс\n\n"

        if "platforms" in stats and stats["platforms"]:
            message += "**Платформы:**\n"
            for platform, count in stats["platforms"].items():
                message += f"• {platform}: {count}\n"
        else:
            message += "**Платформы:** нет данных\n"

        return message

    def _format_calculation_timestamp_line(self) -> str:
        """Создать строку со штампом времени расчёта и часовым поясом."""
        current_time = self._clock()
        offset = current_time.utcoffset()

        if offset is None:
            offset_str = "+00:00"
        else:
            total_minutes = int(offset.total_seconds() // 60)
            sign = "+" if total_minutes >= 0 else "-"
            total_minutes = abs(total_minutes)
            hours, minutes = divmod(total_minutes, 60)
            offset_str = f"{sign}{hours:02d}:{minutes:02d}"

        formatted_timestamp = current_time.strftime(CALCULATION_TIMESTAMP_FORMAT)
        return CALCULATION_TIMESTAMP_LINE.format(datetime=formatted_timestamp, offset=offset_str)


# Global response formatter instance
response_formatter = ResponseFormatter()
