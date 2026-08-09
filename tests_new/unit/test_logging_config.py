"""Tests for centralized, privacy-preserving runtime logging."""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator

import pytest

from app.config import config
from app.logging_config import SensitiveDataFilter, configure_logging


@pytest.fixture
def preserved_root_logging() -> Iterator[None]:
    """Restore global logging state after tests that configure the root logger."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    third_party_levels = {
        name: logging.getLogger(name).level
        for name in ("httpx", "httpcore", "telegram.ext.ExtBot", "telegram.ext._application")
    }
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)
    for name, level in third_party_levels.items():
        logging.getLogger(name).setLevel(level)


def _format_filtered_message(message: str, *args: object, bot_token: str | None = None) -> str:
    """Format one record through the production sensitive-data filter."""
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=args,
        exc_info=None,
    )
    assert SensitiveDataFilter(bot_token=bot_token).filter(record)
    return logging.Formatter("%(message)s").format(record)


def _configured_stream_handler() -> logging.StreamHandler:
    """Return the stream handler installed by ``configure_logging``."""
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    return handler


def test_sensitive_data_filter_redacts_telegram_api_token() -> None:
    """A Telegram API URL must never expose the bot credential."""
    output = _format_filtered_message(
        "POST %s",
        "https://api.telegram.org/bot123456:ABC_secret/sendMessage",
    )

    assert output == "POST https://api.telegram.org/bot<REDACTED>/sendMessage"
    assert "123456:ABC_secret" not in output


def test_sensitive_data_filter_redacts_configured_webhook_path() -> None:
    """The configured token must be removed even when used as a bare URL path."""
    output = _format_filtered_message(
        "Webhook path: /123456:ABC_secret",
        bot_token="123456:ABC_secret",
    )

    assert output == "Webhook path: /<REDACTED>"
    assert "/123456:ABC_secret" not in output


@pytest.mark.parametrize(
    ("message", "args", "sensitive_values"),
    [
        (
            "User %s (@%s) sent message: %s",
            ("987654321", "private_user", "my full private message"),
            ("987654321", "private_user", "my full private message"),
        ),
        (
            "Received Update(update_id=44, message=Message(chat_id=987654321, "
            "username='private_user', text='my full private message'))",
            (),
            ("987654321", "private_user", "my full private message", "update_id=44"),
        ),
        (
            "Telegram payload: {'chat_id': 987654321, 'username': 'private_user', "
            "'text': 'my full private message'}",
            (),
            ("987654321", "private_user", "my full private message"),
        ),
        (
            "Configuration admin_chat_id=987654321",
            (),
            ("987654321",),
        ),
        (
            "Telegram chat=Chat(id=987654321, username='private_user')",
            (),
            ("987654321", "private_user"),
        ),
        (
            "Message('my full private message')",
            (),
            ("my full private message",),
        ),
        (
            "Incoming message my full private message",
            (),
            ("my full private message",),
        ),
        (
            "Received user text my full private message",
            (),
            ("my full private message",),
        ),
        (
            "Telegram payload: {'chat': {'id': 987654321}}",
            (),
            ("987654321",),
        ),
    ],
)
def test_sensitive_data_filter_removes_telegram_personal_data(
    message: str,
    args: tuple[object, ...],
    sensitive_values: tuple[str, ...],
) -> None:
    """Configured logs must not emit Telegram identity or message content."""
    output = _format_filtered_message(message, *args)

    for value in sensitive_values:
        assert value not in output


def test_configure_logging_preserves_normal_logs_and_limits_network_noise(
    preserved_root_logging: None,
) -> None:
    """Runtime setup keeps application logs while silencing verbose network clients."""
    configure_logging("DEBUG")

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert any(isinstance(item, SensitiveDataFilter) for item in root.handlers[0].filters)
    for name in ("httpx", "httpcore", "telegram.ext.ExtBot", "telegram.ext._application"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING

    stream = io.StringIO()
    _configured_stream_handler().setStream(stream)
    logging.getLogger("app.services.cache_service").info("Cache service closed")

    assert "INFO - Cache service closed" in stream.getvalue()


def test_configure_logging_redacts_the_configured_webhook_token(
    preserved_root_logging: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime configuration must pass its token to the output redactor."""
    token = "123456:ABC_secret"
    monkeypatch.setattr(config.bot, "bot_token", token)
    configure_logging("INFO")
    stream = io.StringIO()
    _configured_stream_handler().setStream(stream)

    logging.getLogger("app.main").warning("Webhook path: /%s", token)

    assert token not in stream.getvalue()
    assert "/<REDACTED>" in stream.getvalue()


def test_configured_logging_redacts_credentials_from_exception_text(
    preserved_root_logging: None,
) -> None:
    """Exception formatting must not bypass the handler's credential filter."""
    token = "123456:ABC_secret"
    configure_logging("INFO")
    stream = io.StringIO()
    _configured_stream_handler().setStream(stream)

    try:
        raise RuntimeError(f"request failed for bot{token}")
    except RuntimeError:
        logging.getLogger("app.main").exception("Telegram request failed")

    assert token not in stream.getvalue()
    assert "bot<REDACTED>" in stream.getvalue()
