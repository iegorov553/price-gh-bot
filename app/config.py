"""Configuration management for the price bot."""

import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml
try:
    from pydantic_settings import BaseSettings
    from pydantic import Field
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings, Field


class ShippingConfig(BaseSettings):
    """Shopfans shipping configuration."""
    base_cost: float = 13.99
    per_kg_rate: float = 14.0
    light_threshold: float = 0.45
    light_handling_fee: float = 3.0
    heavy_handling_fee: float = 5.0


class CommissionConfig(BaseSettings):
    """Commission structure configuration."""
    fixed_amount: float = 15.0
    fixed_threshold: float = 150.0
    percentage_rate: float = 0.10


class CurrencyConfig(BaseSettings):
    """Currency exchange configuration."""
    markup_percentage: float = 5.0
    default_source: str = "cbr"
    fallback_enabled: bool = False


class BotConfig(BaseSettings):
    """Main bot configuration."""
    bot_token: str = Field(..., env="BOT_TOKEN")
    admin_chat_id: int = 26917201
    port: int = Field(default=8000, env="PORT")
    railway_domain: Optional[str] = Field(default=None, env="RAILWAY_PUBLIC_DOMAIN")
    railway_url: Optional[str] = Field(default=None, env="RAILWAY_URL")
    timeout: int = 20

    @property
    def webhook_domain(self) -> Optional[str]:
        """Get webhook domain for Railway deployment."""
        return self.railway_domain or self.railway_url

    @property
    def use_webhook(self) -> bool:
        """Determine if webhook mode should be used."""
        return bool(self.webhook_domain)


class Config:
    """Application configuration manager."""
    
    def __init__(self, config_dir: Optional[Path] = None):
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
            self.shipping = ShippingConfig(
                base_cost=shopfans_data.get("base_cost", 13.99),
                per_kg_rate=shopfans_data.get("per_kg_rate", 14.0),
                light_threshold=shopfans_data.get("light_threshold", 0.45),
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
    
    def _load_shipping_patterns(self) -> List[Dict[str, Any]]:
        """Load shipping weight patterns from YAML."""
        shipping_path = self.config_dir / "shipping_table.yml"
        if not shipping_path.exists():
            return []
        
        with open(shipping_path) as f:
            data = yaml.safe_load(f)
        
        return data.get("patterns", [])
    
    @property
    def default_shipping_weight(self) -> float:
        """Get default shipping weight."""
        shipping_path = self.config_dir / "shipping_table.yml"
        if not shipping_path.exists():
            return 0.60
        
        with open(shipping_path) as f:
            data = yaml.safe_load(f)
        
        return data.get("default_weight", 0.60)


# Global configuration instance
config = Config()