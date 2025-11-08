"""Simple unit tests for Grailed availability functionality.

Tests the new error handling logic without complex async mocking.
"""


from app.bot.messages import GRAILED_LISTING_ISSUE, GRAILED_SITE_DOWN, GRAILED_SITE_SLOW


class TestGrailedAvailabilityMessages:
    """Test message formatting for different availability scenarios."""

    def test_grailed_listing_issue_message(self):
        """Test listing-specific issue message formatting."""
        expected_keywords = [
            "Не удалось получить цену товара",
            "Сайт Grailed работает нормально",
            "Товар мог быть удален",
            "Ссылка может быть неактивной",
            "Попробуйте другую ссылку",
        ]

        for keyword in expected_keywords:
            assert keyword in GRAILED_LISTING_ISSUE

    def test_grailed_site_down_message(self):
        """Test site down message formatting."""
        message = GRAILED_SITE_DOWN.format(status_code=500, response_time=5000)

        expected_keywords = [
            "Не удалось получить цену товара",
            "сайт Grailed временно недоступен",
            "HTTP 500",
            "5000мс",
            "Попробуйте позже",
        ]

        for keyword in expected_keywords:
            assert keyword in message

    def test_grailed_site_slow_message(self):
        """Test slow site message formatting."""
        message = GRAILED_SITE_SLOW.format(response_time=8000)

        expected_keywords = [
            "Не удалось получить цену товара",
            "сайт Grailed работает медленно",
            "8000мс",
            "повторить запрос через несколько минут",
        ]

        for keyword in expected_keywords:
            assert keyword in message


class TestGrailedErrorHandlingLogic:
    """Test the logic flow of Grailed error handling."""

    def test_availability_check_result_parsing(self):
        """Test parsing of availability check results via response formatter."""
        from app.bot.response_formatter import response_formatter

        formatter = response_formatter

        # Test case 1: Site available, listing issue
        result_listing_issue = {
            "success": False,
            "platform": "grailed",
            "error": "Listing not found or removed",
        }
        message = formatter._format_error_response(result_listing_issue)  # noqa: SLF001 - testing internal helper
        assert "Сайт Grailed работает нормально" in message

        # Test case 2: Site down
        result_site_down = {
            "success": False,
            "platform": "grailed",
            "error": "HTTP 500 error from main page",
        }
        message = formatter._format_error_response(result_site_down)
        assert "временно недоступен" in message

        # Test case 3: Site timeout / slow
        result_site_slow = {
            "success": False,
            "platform": "grailed",
            "error": "Connection timeout - site may be slow",
        }
        message = formatter._format_error_response(result_site_slow)
        assert "работает медленно" in message

    def test_grailed_url_detection(self):
        """Test Grailed URL detection logic."""
        from app.scrapers.grailed import is_grailed_url

        # Valid Grailed URLs
        valid_urls = [
            "https://www.grailed.com/listings/123456-item-name",
            "http://grailed.com/listings/789",
            "https://grailed.com/username",
            "https://www.grailed.com/search",
        ]

        for url in valid_urls:
            assert is_grailed_url(url), f"Should detect {url} as Grailed URL"

        # Invalid URLs
        invalid_urls = [
            "https://www.ebay.com/itm/123456",
            "https://example.com/grailed",
            "https://fakesite.com/listings/123",
            "not-a-url",
        ]

        for url in invalid_urls:
            assert not is_grailed_url(url), f"Should NOT detect {url} as Grailed URL"
