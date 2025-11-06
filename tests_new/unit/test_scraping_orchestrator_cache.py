"""Tests for scraping orchestrator cache validation."""

from decimal import Decimal

from app.bot.scraping_orchestrator import ScrapingOrchestrator
from app.models import ItemData


class TestScrapingOrchestratorCache:
    def setup_method(self) -> None:
        self.orchestrator = ScrapingOrchestrator()

    def test_cached_result_with_price_is_valid(self) -> None:
        cached = {
            "success": True,
            "item_data": ItemData(price=Decimal("100.00")),
            "platform": "grailed",
        }
        assert self.orchestrator._is_cached_result_valid(cached) is True

    def test_cached_result_without_price_is_invalid(self) -> None:
        cached = {
            "success": True,
            "item_data": ItemData(),
            "platform": "grailed",
        }
        assert self.orchestrator._is_cached_result_valid(cached) is False
