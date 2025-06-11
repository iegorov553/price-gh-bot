"""Configuration management for the price bot.

Handles all application configuration including environment variables, YAML
config files, and default settings. Provides structured configuration classes
for different aspects of the application (bot, shipping, currency, etc.).
"""

from pathlib import Path
from typing import Any

import yaml

try:
    from pydantic import Field
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings, Field


class ShippingConfig(BaseSettings):
    """Shopfans shipping cost calculation parameters with tiered pricing.
    
    Attributes:
        base_cost: Minimum shipping cost in USD.
        per_kg_rate_europe: Cost per kilogram for Europe route (< $200).
        per_kg_rate_turkey: Cost per kilogram for Turkey route (>= $200).
        per_kg_rate_kazakhstan: Cost per kilogram for Kazakhstan route (>= $1000).
        turkey_threshold: Order total threshold for Turkey route.
        kazakhstan_threshold: Order total threshold for Kazakhstan route.
        light_threshold: Weight threshold for light item handling fee.
        light_handling_fee: Additional fee for items under threshold.
        heavy_handling_fee: Additional fee for items over threshold.
    """
    base_cost: float = 13.99
    per_kg_rate_europe: float = 30.86
    per_kg_rate_turkey: float = 35.27
    per_kg_rate_kazakhstan: float = 41.89
    turkey_threshold: float = 200.0
    kazakhstan_threshold: float = 1000.0
    light_threshold: float = 1.36  # 3 pounds
    light_handling_fee: float = 3.0
    heavy_handling_fee: float = 5.0


class CommissionConfig(BaseSettings):
    """Commission fee structure configuration.
    
    Attributes:
        fixed_amount: Fixed commission for items under threshold.
        fixed_threshold: Price threshold for switching to percentage.
        percentage_rate: Commission rate for expensive items (0.10 = 10%).
    """
    fixed_amount: float = 15.0
    fixed_threshold: float = 150.0
    percentage_rate: float = 0.10


class CurrencyConfig(BaseSettings):
    """Currency conversion settings.
    
    Attributes:
        markup_percentage: Markup added to base exchange rate.
        default_source: Primary exchange rate API source.
        fallback_enabled: Whether to use fallback rate sources.
    """
    markup_percentage: float = 5.0
    default_source: str = "cbr"
    fallback_enabled: bool = False


class BotConfig(BaseSettings):
    """Main Telegram bot configuration.
    
    Attributes:
        bot_token: Telegram bot API token from environment.
        admin_chat_id: Telegram chat ID for admin notifications.
        port: Server port for webhook mode.
        railway_domain: Railway public domain for webhooks.
        railway_url: Railway URL for webhooks (fallback).
        timeout: HTTP request timeout in seconds.
        enable_headless_browser: Whether to use headless browser for extraction.
    """
    bot_token: str = Field(..., env="BOT_TOKEN")
    admin_chat_id: int = 26917201
    port: int = Field(default=8000, env="PORT")
    railway_domain: str | None = Field(default=None, env="RAILWAY_PUBLIC_DOMAIN")
    railway_url: str | None = Field(default=None, env="RAILWAY_URL")
    timeout: int = 20
    enable_headless_browser: bool = Field(default=True, env="ENABLE_HEADLESS_BROWSER")

    @property
    def webhook_domain(self) -> str | None:
        """Get webhook domain for Railway deployment.
        
        Returns:
            Domain string if available, None for polling mode.
        """
        return self.railway_domain or self.railway_url

    @property
    def use_webhook(self) -> bool:
        """Determine if webhook mode should be used.
        
        Returns:
            True if webhook domain is configured, False for polling mode.
        """
        return bool(self.webhook_domain)


class Config:
    """Application configuration manager.
    
    Centralizes loading and management of all configuration sources including
    environment variables, YAML files, and default values. Provides typed
    access to configuration sections for different application components.
    """

    def __init__(self, config_dir: Path | None = None):
        """Initialize configuration manager.
        
        Args:
            config_dir: Path to configuration directory, defaults to app/config.
        """
        if config_dir is None:
            config_dir = Path(__file__).parent / "config"

        self.config_dir = Path(config_dir)

        # Load main configurations
        self.bot = BotConfig()

        # Load fee configuration
        fees_path = self.config_dir / "fees.yml"
        if fees_path.exists():
            with open(fees_path) as f:
                fees_data = yaml.safe_load(f)

            commission_data = fees_data.get("commission", {})
            self.commission = CommissionConfig(
                fixed_amount=commission_data.get("fixed", {}).get("amount", 15.0),
                fixed_threshold=commission_data.get("fixed", {}).get("threshold", 150.0),
                percentage_rate=commission_data.get("percentage", {}).get("rate", 0.10)
            )

            shopfans_data = fees_data.get("shopfans", {})
            per_kg_rates = shopfans_data.get("per_kg_rates", {})
            rate_thresholds = shopfans_data.get("rate_thresholds", {})
            self.shipping = ShippingConfig(
                base_cost=shopfans_data.get("base_cost", 13.99),
                per_kg_rate_europe=per_kg_rates.get("europe", 30.86),
                per_kg_rate_turkey=per_kg_rates.get("turkey", 35.27),
                per_kg_rate_kazakhstan=per_kg_rates.get("kazakhstan", 41.89),
                turkey_threshold=rate_thresholds.get("turkey", 200.0),
                kazakhstan_threshold=rate_thresholds.get("kazakhstan", 1000.0),
                light_threshold=shopfans_data.get("light_threshold", 1.36),
                light_handling_fee=shopfans_data.get("handling_fee", {}).get("light_items", 3.0),
                heavy_handling_fee=shopfans_data.get("handling_fee", {}).get("heavy_items", 5.0)
            )

            currency_data = fees_data.get("currency", {})
            self.currency = CurrencyConfig(
                markup_percentage=currency_data.get("markup_percentage", 5.0),
                default_source=currency_data.get("default_source", "cbr"),
                fallback_enabled=currency_data.get("fallback_enabled", False)
            )
        else:
            # Use defaults if config file not found
            self.commission = CommissionConfig()
            self.shipping = ShippingConfig()
            self.currency = CurrencyConfig()

        # Load shipping patterns
        self.shipping_patterns = self._load_shipping_patterns()

    def _load_shipping_patterns(self) -> list[dict[str, Any]]:
        """Load shipping weight patterns from YAML configuration.
        
        Returns:
            List of pattern dictionaries with 'pattern' and 'weight' keys.
        """
        shipping_path = self.config_dir / "shipping_table.yml"
        if not shipping_path.exists():
            return []

        with open(shipping_path) as f:
            data = yaml.safe_load(f)

        return data.get("patterns", [])

    @property
    def default_shipping_weight(self) -> float:
        """Get default shipping weight for unmatched items.
        
        Returns:
            Default weight in kilograms, falls back to 0.60kg.
        """
        shipping_path = self.config_dir / "shipping_table.yml"
        if not shipping_path.exists():
            return 0.60

        with open(shipping_path) as f:
            data = yaml.safe_load(f)

        return data.get("default_weight", 0.60)


# Global configuration instance
config = Config()
