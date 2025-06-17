"""Global test configuration and fixtures.

Provides shared fixtures for all test levels including mocked configurations,
test data, and environment setup. Ensures test isolation and consistency.
"""

import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

# Test constants
TEST_BOT_TOKEN = os.getenv("TEST_BOT_TOKEN", "test_bot_token_placeholder")
TEST_ADMIN_CHAT_ID = int(os.getenv("TEST_ADMIN_CHAT_ID", "12345"))

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def test_environment():
    """Setup test environment variables for all tests."""
    test_env = {
        'BOT_TOKEN': TEST_BOT_TOKEN,
        'ADMIN_CHAT_ID': str(TEST_ADMIN_CHAT_ID),
        'ENABLE_HEADLESS_BROWSER': 'false',
        'ENVIRONMENT': 'test',
        'LOG_LEVEL': 'DEBUG'
    }
    
    # Store original values
    original_env = {}
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    yield
    
    # Restore original values
    for key, original_value in original_env.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value


@pytest.fixture
def mock_config():
    """Mock the global config object with test values."""
    with patch('app.config.config') as mock_config_obj:
        # Commission settings
        mock_config_obj.commission.fixed_amount = 15.0
        mock_config_obj.commission.fixed_threshold = 150.0
        mock_config_obj.commission.percentage_rate = 0.10
        
        # Shipping settings
        mock_config_obj.shipping.base_cost = 13.99
        mock_config_obj.shipping.per_kg_rate = 14.0
        mock_config_obj.shipping.light_threshold = 0.45
        mock_config_obj.shipping.light_handling_fee = 3.0
        mock_config_obj.shipping.heavy_handling_fee = 5.0
        mock_config_obj.default_shipping_weight = 0.60
        
        # Bot settings
        mock_config_obj.bot.admin_chat_id = TEST_ADMIN_CHAT_ID
        mock_config_obj.bot.timeout = 30
        mock_config_obj.bot.enable_headless_browser = False
        
        # Shipping patterns
        mock_config_obj.shipping_patterns = [
            {"pattern": r"hoodie|sweatshirt|pullover", "weight": 0.80},
            {"pattern": r"t-shirt|tee|tank", "weight": 0.25},
            {"pattern": r"sneakers|shoes|boots", "weight": 1.40},
            {"pattern": r"tie|necktie|bow tie", "weight": 0.08},
        ]
        
        yield mock_config_obj


@pytest.fixture
def sample_item_data():
    """Sample ItemData objects for testing."""
    from app.models import ItemData
    
    return {
        'ebay_item': ItemData(
            price=Decimal("89.99"),
            shipping_us=Decimal("12.50"),
            is_buyable=True,
            title="Nike Air Jordan 1 High OG Chicago"
        ),
        'grailed_item': ItemData(
            price=Decimal("120.00"),
            shipping_us=Decimal("15.00"),
            is_buyable=True,
            title="Supreme Box Logo Hoodie Black Large"
        ),
        'high_value_item': ItemData(
            price=Decimal("200.00"),
            shipping_us=Decimal("25.00"),
            is_buyable=True,
            title="Off-White x Nike Air Presto"
        ),
        'no_shipping_item': ItemData(
            price=Decimal("150.00"),
            shipping_us=Decimal("0.00"),
            is_buyable=True,
            title="Local pickup item"
        )
    }


@pytest.fixture
def sample_seller_data():
    """Sample SellerData objects for testing."""
    from datetime import datetime, UTC
    from app.models import SellerData
    
    return {
        'excellent_seller': SellerData(
            num_reviews=250,
            avg_rating=4.9,
            trusted_badge=True,
            last_updated=datetime.now(UTC)
        ),
        'good_seller': SellerData(
            num_reviews=50,
            avg_rating=4.5,
            trusted_badge=False,
            last_updated=datetime.now(UTC)
        ),
        'poor_seller': SellerData(
            num_reviews=5,
            avg_rating=3.2,
            trusted_badge=False,
            last_updated=datetime.now(UTC)
        ),
        'no_data': SellerData(
            num_reviews=0,
            avg_rating=0.0,
            trusted_badge=False,
            last_updated=datetime.now(UTC)
        )
    }


@pytest.fixture
def mock_http_session():
    """Mock aiohttp.ClientSession for testing HTTP requests."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    
    # Mock successful response
    response = AsyncMock()
    response.status = 200
    response.text = AsyncMock(return_value="<html>Test content</html>")
    response.json = AsyncMock(return_value={"test": "data"})
    
    session.get.return_value.__aenter__.return_value = response
    session.post.return_value.__aenter__.return_value = response
    
    return session


@pytest.fixture
def sample_exchange_rate():
    """Sample currency exchange rate data."""
    from datetime import datetime
    from app.models import CurrencyRate
    
    return CurrencyRate(
        from_currency="USD",
        to_currency="RUB",
        rate=Decimal("95.50"),
        source="cbr",
        fetched_at=datetime.now(),
        markup_percentage=5.0
    )


@pytest.fixture
def test_urls():
    """Collection of real URLs for testing scrapers."""
    return {
        'ebay': [
            "https://www.ebay.com/itm/123456789",  # Will use real URLs in e2e tests
        ],
        'grailed': [
            "https://www.grailed.com/listings/123456-nike-air-jordan-1",  # Will use real URLs
            "https://grailed.com/username",  # Profile URL
        ],
        'grailed_shortlinks': [
            "https://grailed.app.link/abc123",
        ]
    }


@pytest.fixture
def load_test_fixtures():
    """Load test fixtures from JSON files."""
    def _load_fixture(filename: str):
        fixture_path = Path(__file__).parent / "fixtures" / filename
        if fixture_path.exists():
            with open(fixture_path, 'r') as f:
                return json.load(f)
        return {}
    
    return _load_fixture


# Commission calculation test cases
@pytest.fixture
def commission_test_cases():
    """Comprehensive test cases for commission calculation."""
    return [
        # (item_price, us_shipping, expected_commission, commission_type, description)
        (80, 20, 15.00, "fixed", "Below threshold with shipping"),
        (120, 40, 16.00, "percentage", "Above threshold due to shipping"),
        (200, 50, 25.00, "percentage", "High value with high shipping"),
        (200, 0, 20.00, "percentage", "High value without US shipping"),
        (149, 0, 15.00, "fixed", "Just below threshold"),
        (150, 0, 15.00, "percentage", "Exactly at threshold"),
        (100, 50, 15.00, "percentage", "Low item, high shipping above threshold"),
        (50, 10, 15.00, "fixed", "Low value item with low shipping"),
    ]


# Shipping calculation test cases  
@pytest.fixture
def shipping_test_cases():
    """Test cases for shipping weight estimation."""
    return [
        ("Supreme hoodie black large", 0.80, "hoodie pattern"),
        ("Nike Air Jordan 1 sneakers size 10", 1.40, "sneakers pattern"),
        ("Vintage band t-shirt", 0.25, "t-shirt pattern"),
        ("Silk tie navy blue", 0.08, "tie pattern"),
        ("Random item description", 0.60, "default weight"),
        ("", 0.60, "empty title default"),
    ]


@pytest.fixture
def mock_telegram_bot():
    """Mock Telegram bot for testing handlers."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    
    # Mock update and context
    update = MagicMock()
    update.message.text = "Test message"
    update.message.reply_text = AsyncMock()
    
    context = MagicMock()
    
    return {
        'bot': bot,
        'update': update,
        'context': context
    }


@pytest.fixture
def mock_cbr_api():
    """Mock Central Bank of Russia API responses."""
    xml_response = '''<?xml version="1.0" encoding="windows-1251"?>
    <ValCurs Date="09.06.2025" name="Foreign Currency Market">
        <Valute ID="R01235">
            <NumCode>840</NumCode>
            <CharCode>USD</CharCode>
            <Nominal>1</Nominal>
            <Name>Доллар США</Name>
            <Value>95,5000</Value>
        </Valute>
    </ValCurs>'''
    
    return xml_response


@pytest.fixture
def clean_config_cache():
    """Clean config cache before and after tests."""
    # Clear any cached config
    yield
    # Cleanup after test
    pass