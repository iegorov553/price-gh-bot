"""Unit tests for configuration models, including GrailedAlgoliaConfig."""

import pytest

from app.config import Config, GrailedAlgoliaConfig
from app.models import ItemData


def test_grailed_algolia_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """GrailedAlgoliaConfig should have correct default values."""
    monkeypatch.delenv("GRAILED_ALGOLIA_APP_ID", raising=False)
    monkeypatch.delenv("GRAILED_ALGOLIA_API_KEY", raising=False)
    monkeypatch.delenv("GRAILED_ALGOLIA_INDEX_NAME", raising=False)
    monkeypatch.delenv("GRAILED_ALGOLIA_SOLD_INDEX_NAME", raising=False)
    monkeypatch.delenv("GRAILED_ALGOLIA_TIMEOUT_SEC", raising=False)

    cfg = GrailedAlgoliaConfig()

    assert cfg.app_id == "MNRWEFSS2Q"
    assert cfg.api_key == "c89dbaddf15fe70e1941a109bf7c2a3d"
    assert cfg.index_name == "Listing_production"
    assert cfg.sold_index_name == "Listing_sold_production"
    assert cfg.timeout_sec == 5.0


def test_grailed_algolia_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """GrailedAlgoliaConfig should respect environment variables."""
    monkeypatch.setenv("GRAILED_ALGOLIA_APP_ID", "CUSTOM_APP_ID")
    monkeypatch.setenv("GRAILED_ALGOLIA_API_KEY", "custom_key")
    monkeypatch.setenv("GRAILED_ALGOLIA_INDEX_NAME", "custom_index")
    monkeypatch.setenv("GRAILED_ALGOLIA_SOLD_INDEX_NAME", "custom_sold_index")
    monkeypatch.setenv("GRAILED_ALGOLIA_TIMEOUT_SEC", "10.5")

    cfg = GrailedAlgoliaConfig()

    assert cfg.app_id == "CUSTOM_APP_ID"
    assert cfg.api_key == "custom_key"
    assert cfg.index_name == "custom_index"
    assert cfg.sold_index_name == "custom_sold_index"
    assert cfg.timeout_sec == 10.5


def test_config_includes_algolia_instance() -> None:
    """Config manager should provide an algolia configuration attribute."""
    cfg = Config()
    assert hasattr(cfg, "algolia")
    assert isinstance(cfg.algolia, GrailedAlgoliaConfig)


def test_item_data_is_sold_default_and_assignment() -> None:
    """ItemData should have is_sold defaulting to False and support assignment."""
    item = ItemData()
    assert item.is_sold is False

    sold_item = ItemData(is_sold=True)
    assert sold_item.is_sold is True
