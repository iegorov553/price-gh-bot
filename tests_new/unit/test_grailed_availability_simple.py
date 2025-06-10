"""Simple unit tests for Grailed availability functionality.

Tests the new error handling logic without complex async mocking.
"""

import pytest
from unittest.mock import AsyncMock, patch

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
            "Попробуйте другую ссылку"
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
            "Попробуйте позже"
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
            "повторить запрос через несколько минут"
        ]
        
        for keyword in expected_keywords:
            assert keyword in message


class TestGrailedErrorHandlingLogic:
    """Test the logic flow of Grailed error handling."""

    @pytest.mark.asyncio
    async def test_availability_check_result_parsing(self):
        """Test parsing of availability check results."""
        from app.bot.handlers import _handle_grailed_scraping_failure
        from app.scrapers import grailed
        
        # Mock update object
        class MockMessage:
            def __init__(self):
                self.sent_message = None
                
            async def reply_text(self, text):
                self.sent_message = text
        
        class MockUpdate:
            def __init__(self):
                self.message = MockMessage()
        
        update = MockUpdate()
        mock_session = AsyncMock()
        
        # Test case 1: Site available, listing issue
        with patch.object(grailed, 'check_grailed_availability') as mock_check:
            mock_check.return_value = {
                'is_available': True,
                'status_code': 200,
                'response_time_ms': 1000,
                'error_message': None
            }
            
            await _handle_grailed_scraping_failure(update, mock_session)
            assert "Сайт Grailed работает нормально" in update.message.sent_message
        
        # Test case 2: Site down
        with patch.object(grailed, 'check_grailed_availability') as mock_check:
            mock_check.return_value = {
                'is_available': False,
                'status_code': 500,
                'response_time_ms': 5000,
                'error_message': 'HTTP 500 error from main page'
            }
            
            await _handle_grailed_scraping_failure(update, mock_session)
            assert "временно недоступен" in update.message.sent_message
            assert "500" in update.message.sent_message
        
        # Test case 3: Site timeout
        with patch.object(grailed, 'check_grailed_availability') as mock_check:
            mock_check.return_value = {
                'is_available': False,
                'status_code': None,
                'response_time_ms': 10000,
                'error_message': 'Connection timeout - site may be slow'
            }
            
            await _handle_grailed_scraping_failure(update, mock_session)
            assert "работает медленно" in update.message.sent_message
            assert "10000мс" in update.message.sent_message

    def test_grailed_url_detection(self):
        """Test Grailed URL detection logic."""
        from app.scrapers.grailed import is_grailed_url
        
        # Valid Grailed URLs
        valid_urls = [
            "https://www.grailed.com/listings/123456-item-name",
            "http://grailed.com/listings/789",
            "https://grailed.com/username",
            "https://www.grailed.com/search"
        ]
        
        for url in valid_urls:
            assert is_grailed_url(url), f"Should detect {url} as Grailed URL"
        
        # Invalid URLs
        invalid_urls = [
            "https://www.ebay.com/itm/123456",
            "https://example.com/grailed",
            "https://fakesite.com/listings/123",
            "not-a-url"
        ]
        
        for url in invalid_urls:
            assert not is_grailed_url(url), f"Should NOT detect {url} as Grailed URL"