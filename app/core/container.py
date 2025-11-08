"""Dependency-injection container.

This module defines a dependency-injection (DI) container that wires together
the application's components. This approach to DI helps to decouple the
application's components and makes them easier to test and maintain.
"""

from dependency_injector import containers, providers

from app.bot.analytics_tracker import AnalyticsTracker
from app.bot.response_formatter import ResponseFormatter
from app.bot.scraping_orchestrator import ScrapingOrchestrator
from app.bot.url_processor import URLProcessor
from app.services.analytics import AnalyticsService
from app.services.browser_pool import BrowserPool
from app.services.cache_service import CacheService
from app.services.currency import OptimizedCurrencyService
from app.services.customs import CustomsService
from app.services.github import GitHubService
from app.services.shipping import ShippingService


class Container(containers.DeclarativeContainer):
    """DI container for the application.

    This container holds the wiring for all the application's components.
    """

    config = providers.Configuration()

    # Services
    analytics_service = providers.Singleton(AnalyticsService, db_path=config.analytics.db_path)
    browser_pool = providers.Singleton(BrowserPool)
    cache_service = providers.Singleton(CacheService, config=config.cache)
    currency_service = providers.Singleton(OptimizedCurrencyService)
    customs_service = providers.Singleton(CustomsService)
    github_service = providers.Singleton(GitHubService)
    shipping_service = providers.Singleton(ShippingService)

    # Bot components
    analytics_tracker = providers.Singleton(AnalyticsTracker, analytics_service=analytics_service)
    response_formatter = providers.Singleton(ResponseFormatter)
    scraping_orchestrator = providers.Singleton(ScrapingOrchestrator)
    url_processor = providers.Singleton(URLProcessor)
