"""Centralized runtime logging with Telegram credential redaction."""

from __future__ import annotations

import logging
import re

from .config import config

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
_TELEGRAM_TOKEN_PATTERN = re.compile(r"bot\d+:[A-Za-z0-9_-]+")
_RAW_TELEGRAM_DATA_PATTERNS = (
    re.compile(r"\bUpdate\s*\(", re.IGNORECASE),
    re.compile(r"[\"']?update_id[\"']?\s*[:=]", re.IGNORECASE),
    re.compile(r"\b(?:Chat|User|Message)\s*\(", re.IGNORECASE),
    re.compile(r"[\"']?(?:chat|from|user|message)[\"']?\s*:\s*\{", re.IGNORECASE),
)
_LABELED_IDENTITY_PATTERN = re.compile(
    r"\b((?:admin_)?chat[_ ]?id|user[_ ]?id|username)\b([\"']?\s*[:=]\s*)"
    r"(?:'[^']*'|\"[^\"]*\"|@?[A-Za-z0-9_-]+|-?\d+)",
    re.IGNORECASE,
)
_POSITIONAL_ID_PATTERN = re.compile(r"\b(user|admin)\s+-?\d{3,}\b", re.IGNORECASE)
_USERNAME_PATTERN = re.compile(r"(?<![\w@])@[A-Za-z0-9_]+")
_MESSAGE_CONTENT_PATTERN = re.compile(
    r"\b(message(?:_text)?|text|admin notification sent)\b([\"']?\s*[:=]\s*).*$",
    re.IGNORECASE,
)
_MESSAGE_PREFIX_PATTERN = re.compile(
    r"\b((?:incoming|received)\s+(?:user\s+)?(?:message|text))\b.*$",
    re.IGNORECASE,
)


class SensitiveDataFilter(logging.Filter):
    """Remove Telegram credentials and personal data before records are emitted."""

    def __init__(self, bot_token: str | None = None) -> None:
        """Initialize the filter with the configured token when available."""
        super().__init__()
        self._bot_token = bot_token if bot_token is not None else config.bot.bot_token

    def redact(self, value: str) -> str:
        """Return a log-safe representation of a formatted record value."""
        if any(pattern.search(value) for pattern in _RAW_TELEGRAM_DATA_PATTERNS):
            return "<REDACTED TELEGRAM UPDATE>"

        redacted = _TELEGRAM_TOKEN_PATTERN.sub("bot<REDACTED>", value)
        if self._bot_token:
            redacted = redacted.replace(f"/{self._bot_token}", "/<REDACTED>")
            redacted = redacted.replace(self._bot_token, "<REDACTED>")
        redacted = _LABELED_IDENTITY_PATTERN.sub(r"\1\2<REDACTED>", redacted)
        redacted = _POSITIONAL_ID_PATTERN.sub(r"\1 <REDACTED>", redacted)
        redacted = _USERNAME_PATTERN.sub("@<REDACTED>", redacted)
        redacted = _MESSAGE_CONTENT_PATTERN.sub(r"\1\2<REDACTED>", redacted)
        return _MESSAGE_PREFIX_PATTERN.sub(r"\1 <REDACTED>", redacted)

    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitize the rendered message while preserving normal log records."""
        record.msg = self.redact(record.getMessage())
        record.args = ()
        if record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        return True


class _SensitiveFormatter(logging.Formatter):
    """Apply the same redaction to exception text produced during formatting."""

    def __init__(self, redactor: SensitiveDataFilter) -> None:
        super().__init__(LOG_FORMAT)
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        """Format a record and sanitize any exception or stack text it contains."""
        return self._redactor.redact(super().format(record))


def configure_logging(level: str) -> None:
    """Configure application logging with safe defaults and network noise limits."""
    numeric_level = logging.getLevelNamesMapping()[level.upper()]

    root_logger = logging.getLogger()
    for existing_handler in root_logger.handlers[:]:
        root_logger.removeHandler(existing_handler)

    redactor = SensitiveDataFilter()
    handler = logging.StreamHandler()
    handler.addFilter(redactor)
    handler.setFormatter(_SensitiveFormatter(redactor))
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)

    for logger_name in ("httpx", "httpcore", "telegram.ext.ExtBot", "telegram.ext.Application"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
