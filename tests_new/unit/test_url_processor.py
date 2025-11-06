"""Tests for URL extraction and validation."""

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
