"""Tests for BotConfig security-related settings."""

import pytest

from app.config import BotConfig


def test_bot_config_listen_host_defaults_to_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    """BotConfig should bind to localhost by default for safer webhooks."""
    monkeypatch.delenv("BOT_LISTEN_HOST", raising=False)

    bot_config = BotConfig()

    assert bot_config.listen_host == "127.0.0.1"


def test_bot_config_listen_host_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variable must override listen host when explicitly set."""
    monkeypatch.setenv("BOT_LISTEN_HOST", "0.0.0.0")

    bot_config = BotConfig()

    assert bot_config.listen_host == "0.0.0.0"


def test_bot_config_log_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime logging should default to useful, non-debug output."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    bot_config = BotConfig()

    assert bot_config.log_level == "INFO"


def test_bot_config_log_level_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deployments must be able to opt into a supported logging level."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    bot_config = BotConfig()

    assert bot_config.log_level == "DEBUG"
