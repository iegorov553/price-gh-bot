"""Tests for currency exchange service functionality.

This module contains tests for the currency service that handles:
- USD to RUB exchange rate fetching from CBR API
- Rate caching and error handling
- Currency conversion rate calculations with markup
"""

import pytest
from unittest.mock import AsyncMock, patch
from decimal import Decimal
from datetime import datetime

from app.services.currency import get_usd_to_rub_rate, get_rate, clear_cache


@pytest.mark.asyncio
async def test_get_usd_to_rub_rate_success():
    """Test successful USD to RUB rate fetching."""
    mock_session = AsyncMock()
    
    # Mock CBR XML response
    cbr_xml = """<?xml version="1.0" encoding="windows-1251"?>
    <ValCurs Date="03.02.2023" name="Foreign Currency Market">
        <Valute ID="R01235">
            <NumCode>840</NumCode>
            <CharCode>USD</CharCode>
            <Nominal>1</Nominal>
            <Name>Доллар США</Name>
            <Value>70,0000</Value>
        </Valute>
    </ValCurs>"""
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.read.return_value = cbr_xml.encode('windows-1251')
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    
    rate = await get_usd_to_rub_rate(mock_session)
    
    assert rate is not None
    assert rate.from_currency == "USD"
    assert rate.to_currency == "RUB"
    assert rate.rate == Decimal("73.50")  # 70 * 1.05
    assert rate.source == "cbr"
    assert rate.markup_percentage == 5.0


@pytest.mark.asyncio
async def test_get_usd_to_rub_rate_failure():
    """Test USD to RUB rate fetching failure."""
    mock_session = AsyncMock()
    mock_session.get.side_effect = Exception("Network error")
    
    rate = await get_usd_to_rub_rate(mock_session)
    assert rate is None


@pytest.mark.asyncio
async def test_get_rate_usd_rub():
    """Test get_rate for USD/RUB pair."""
    mock_session = AsyncMock()
    
    with patch('app.services.currency.get_usd_to_rub_rate') as mock_get_usd:
        mock_rate = AsyncMock()
        mock_rate.rate = Decimal("75.00")
        mock_get_usd.return_value = mock_rate
        
        rate = await get_rate("USD", "RUB", mock_session)
        assert rate == mock_rate


@pytest.mark.asyncio
async def test_get_rate_unsupported():
    """Test get_rate for unsupported currency pair."""
    mock_session = AsyncMock()
    
    rate = await get_rate("EUR", "JPY", mock_session)
    assert rate is None


def test_clear_cache():
    """Test cache clearing."""
    clear_cache()  # Should not raise any exceptions