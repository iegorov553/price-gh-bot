"""Russian customs duty calculation service.

Handles calculation of Russian customs duty for items exceeding the 200 EUR threshold.
Uses EUR/USD exchange rate to convert the threshold to USD and applies 15% duty
on the excess amount above the threshold.
"""

import logging
from decimal import Decimal

import aiohttp

from .currency import OptimizedCurrencyService, get_optimized_currency_service

logger = logging.getLogger(__name__)

# Russian customs duty rate for personal imports exceeding 200 EUR
DUTY_RATE = Decimal("0.15")  # 15%
DUTY_THRESHOLD_EUR = Decimal("200")  # 200 EUR threshold


class CustomsService:
    """Calculate Russian customs duty based on configurable currency service."""

    def __init__(self, currency_service: OptimizedCurrencyService):
        """Store currency service used for exchange-rate lookups."""
        self.currency_service = currency_service

    async def calculate_rf_customs_duty(
        self, item_price_usd: Decimal, shipping_us_usd: Decimal, session: aiohttp.ClientSession
    ) -> Decimal:
        """Calculate Russian customs duty for items exceeding 200 EUR threshold.

        Duty applies to personal imports with total value (item + US shipping) > 200 EUR.
        Duty rate: 15% of the amount exceeding 200 EUR.

        Args:
            item_price_usd: Item price in USD
            shipping_us_usd: US shipping cost in USD
            session: aiohttp session for making currency API requests

        Returns:
            Customs duty amount in USD, 0 if below threshold or if EUR/USD rate unavailable
        """
        try:
            # Get EUR/USD exchange rate
            eur_usd_rate = await self.currency_service.get_eur_to_usd_rate_optimized(session)
            if not eur_usd_rate:
                logger.warning("EUR/USD rate unavailable, cannot calculate customs duty")
                return Decimal("0")

            logger.info(f"EUR/USD rate for customs calculation: {eur_usd_rate.rate}")

            # Calculate total value in USD (item + US shipping)
            total_value_usd = item_price_usd + shipping_us_usd

            # Convert 200 EUR threshold to USD
            threshold_usd = DUTY_THRESHOLD_EUR * eur_usd_rate.rate

            logger.info(f"Total value: ${total_value_usd}, Threshold: ${threshold_usd} (200 EUR)")

            # Check if duty applies
            if total_value_usd <= threshold_usd:
                logger.info("Total value below customs threshold, no duty applies")
                return Decimal("0")

            # Calculate excess amount above threshold
            excess_usd = total_value_usd - threshold_usd

            # Calculate 15% duty on excess
            duty_usd = (excess_usd * DUTY_RATE).quantize(Decimal("0.01"))

            logger.info(f"Customs duty calculation: excess ${excess_usd} * 15% = ${duty_usd}")

            return duty_usd

        except Exception as e:
            logger.error(f"Error calculating customs duty: {e}")
            return Decimal("0")

    def get_duty_info(self) -> dict[str, object]:
        """Get information about Russian customs duty rules.

        Returns:
            Dictionary with duty threshold, rate, and description
        """
        return {
            "threshold_eur": DUTY_THRESHOLD_EUR,
            "duty_rate_percent": int(DUTY_RATE * 100),
            "description": "Russian customs duty for personal imports exceeding 200 EUR",
        }


_customs_service: CustomsService | None = None


async def get_customs_service() -> CustomsService:
    """Получить ленивый экземпляр сервиса таможенных пошлин."""
    global _customs_service
    if _customs_service is None:
        currency_service = await get_optimized_currency_service()
        _customs_service = CustomsService(currency_service)
    return _customs_service


async def calculate_rf_customs_duty(
    item_price_usd: Decimal, shipping_us_usd: Decimal, session: aiohttp.ClientSession
) -> Decimal:
    """Функциональная обёртка для обратной совместимости."""
    service = await get_customs_service()
    return await service.calculate_rf_customs_duty(item_price_usd, shipping_us_usd, session)
