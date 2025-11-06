"""Tests for BotConfig security-related settings."""

from app.config import BotConfig


def test_bot_config_listen_host_defaults_to_localhost(monkeypatch) -> None:
    """BotConfig should bind to localhost by default for safer webhooks."""
    monkeypatch.delenv("BOT_LISTEN_HOST", raising=False)

    bot_config = BotConfig()

    assert bot_config.listen_host == "127.0.0.1"


def test_bot_config_listen_host_env_override(monkeypatch) -> None:
    """Environment variable must override listen host when explicitly set."""
    monkeypatch.setenv("BOT_LISTEN_HOST", "0.0.0.0")

    bot_config = BotConfig()

    assert bot_config.listen_host == "0.0.0.0"
