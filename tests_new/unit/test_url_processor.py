"""Tests for URL extraction and validation."""

import logging

import pytest

from app.bot.url_processor import URLProcessor


class TestURLProcessor:
    def setup_method(self) -> None:
        self.processor = URLProcessor()

    def test_extract_url_preserves_query_without_path(self) -> None:
        url = (
            "https://grailed.app.link?channel=Pasteboard&feature=mobile-share"
            "&type=0&duration=0&source=ios&data=abc123"
        )
        text = f"Link: {url}"

        extracted = self.processor.extract_urls(text)

        assert extracted == [url]

    def test_extract_url_strips_trailing_punctuation(self) -> None:
        url = "https://www.grailed.com/listings/123456?foo=bar"
        text = f"({url})."

        extracted = self.processor.extract_urls(text)

        assert extracted == [url]

    def test_suspicious_url_warning_omits_raw_url_and_user_id(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        raw_url = "https://attacker.example/private?secret=raw-value"
        user_id = 918_273_645

        with caplog.at_level(logging.WARNING, logger="app.bot.url_processor"):
            result = self.processor.process_message(raw_url, user_id=user_id)

        assert result["has_suspicious"] is True
        assert "invalid_count=1" in caplog.text
        assert raw_url not in caplog.text
        assert str(user_id) not in caplog.text

    def test_validate_grailed_onelink_url(self) -> None:
        url = "https://grailed.onelink.me/1LT8/7o7iovrk"
        result = self.processor.process_message(url, user_id=12345)

        assert result["valid_urls"] == [url]
        assert result["has_suspicious"] is False
        assert result["categorized"] is not None
        assert url in result["categorized"]["item_listings"]
