"""Contract tests for currency conversion logic.

Tests the currency exchange rate fetching and conversion calculations
to ensure consistent behavior and proper error handling.
"""

import pytest
from decimal import Decimal
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch

from app.services.currency import get_rate, clear_cache
from app.models import CurrencyRate


class TestCurrencyContracts:
    """Test currency conversion contracts."""
    
    def test_successful_exchange_rate_parsing(self, mock_cbr_api, mock_http_session):
        """Test successful parsing of CBR API response."""
        # Setup mock response
        mock_http_session.get.return_value.__aenter__.return_value.text.return_value = mock_cbr_api
        
        # Test the rate fetching
        async def run_test():
            rate = await get_rate("USD", "RUB", mock_http_session)
            
            # Assert rate object is created correctly
            assert isinstance(rate, CurrencyRate)
            assert rate.from_currency == "USD"
            assert rate.to_currency == "RUB"
            assert rate.rate == Decimal("100.28")  # 95.5 * 1.05 (5% markup)
            assert rate.source == "cbr"
            assert rate.markup_percentage == 5.0
            assert isinstance(rate.fetched_at, datetime)
        
        import asyncio
        asyncio.run(run_test())
    
    def test_exchange_rate_markup_calculation(self, mock_cbr_api, mock_http_session):
        """Test that the 5% markup is correctly applied."""
        mock_http_session.get.return_value.__aenter__.return_value.text.return_value = mock_cbr_api
        
        async def run_test():
            rate = await get_rate("USD", "RUB", mock_http_session)
            
            # Base rate from XML is 95.5
            base_rate = Decimal("95.5000")
            expected_rate = base_rate * Decimal("1.05")  # 5% markup
            
            assert rate.rate == expected_rate.quantize(Decimal("0.01"))
            assert rate.markup_percentage == 5.0
        
        import asyncio
        asyncio.run(run_test())
    
    def test_unsupported_currency_pair(self, mock_http_session):
        """Test behavior with unsupported currency pairs."""
        async def run_test():
            # Test unsupported from_currency
            rate = await get_rate("EUR", "RUB", mock_http_session)
            assert rate is None
            
            # Test unsupported to_currency
            rate = await get_rate("USD", "EUR", mock_http_session)
            assert rate is None
            
            # Test both unsupported
            rate = await get_rate("EUR", "JPY", mock_http_session)
            assert rate is None
        
        import asyncio
        asyncio.run(run_test())
    
    def test_malformed_xml_response(self, mock_http_session):
        """Test handling of malformed XML responses."""
        # Setup malformed XML
        malformed_xml = "<invalid>xml</structure>"
        mock_http_session.get.return_value.__aenter__.return_value.text.return_value = malformed_xml
        
        async def run_test():
            rate = await get_rate("USD", "RUB", mock_http_session)
            assert rate is None
        
        import asyncio
        asyncio.run(run_test())
    
    def test_network_error_handling(self, mock_http_session):
        """Test handling of network errors."""
        # Setup network error
        mock_http_session.get.side_effect = Exception("Network error")
        
        async def run_test():
            rate = await get_rate("USD", "RUB", mock_http_session)
            assert rate is None
        
        import asyncio
        asyncio.run(run_test())
    
    def test_missing_usd_in_response(self, mock_http_session):
        """Test handling when USD is not found in CBR response."""
        xml_without_usd = '''<?xml version="1.0" encoding="windows-1251"?>
        <ValCurs Date="09.06.2025" name="Foreign Currency Market">
            <Valute ID="R01239">
                <NumCode>978</NumCode>
                <CharCode>EUR</CharCode>
                <Nominal>1</Nominal>
                <Name>Евро</Name>
                <Value>105,5000</Value>
            </Valute>
        </ValCurs>'''
        
        mock_http_session.get.return_value.__aenter__.return_value.text.return_value = xml_without_usd
        
        async def run_test():
            rate = await get_rate("USD", "RUB", mock_http_session)
            assert rate is None
        
        import asyncio
        asyncio.run(run_test())
    
    def test_cache_functionality(self, mock_cbr_api, mock_http_session):
        """Test that exchange rate caching works correctly."""
        mock_http_session.get.return_value.__aenter__.return_value.text.return_value = mock_cbr_api
        
        async def run_test():
            # Clear cache first
            clear_cache()
            
            # First call should make HTTP request
            rate1 = await get_exchange_rate("USD", "RUB", mock_http_session)
            assert rate1 is not None
            assert mock_http_session.get.call_count == 1
            
            # Second call should use cache
            rate2 = await get_exchange_rate("USD", "RUB", mock_http_session)
            assert rate2 is not None
            assert mock_http_session.get.call_count == 1  # No additional calls
            
            # Rates should be identical
            assert rate1.rate == rate2.rate
            
            # Clear cache and verify new request is made
            clear_cache()
            rate3 = await get_exchange_rate("USD", "RUB", mock_http_session)
            assert rate3 is not None
            assert mock_http_session.get.call_count == 2  # New request made
        
        import asyncio
        asyncio.run(run_test())
    
    def test_decimal_precision(self, mock_http_session):
        """Test that exchange rates maintain proper decimal precision."""
        # XML with precise decimal values
        precise_xml = '''<?xml version="1.0" encoding="windows-1251"?>
        <ValCurs Date="09.06.2025" name="Foreign Currency Market">
            <Valute ID="R01235">
                <NumCode>840</NumCode>
                <CharCode>USD</CharCode>
                <Nominal>1</Nominal>
                <Name>Доллар США</Name>
                <Value>95,1234</Value>
            </Valute>
        </ValCurs>'''
        
        mock_http_session.get.return_value.__aenter__.return_value.text.return_value = precise_xml
        
        async def run_test():
            rate = await get_rate("USD", "RUB", mock_http_session)
            
            # Check precision is maintained through calculation
            base_rate = Decimal("95.1234")
            expected_rate = base_rate * Decimal("1.05")
            
            assert rate.rate == expected_rate.quantize(Decimal("0.01"))
            
            # Verify rate has exactly 2 decimal places
            rate_str = str(rate.rate)
            decimal_part = rate_str.split('.')[1] if '.' in rate_str else "00"
            assert len(decimal_part) <= 2
        
        import asyncio
        asyncio.run(run_test())
    
    def test_currency_rate_model_completeness(self, sample_exchange_rate):
        """Test that CurrencyRate model is properly structured."""
        rate = sample_exchange_rate
        
        # Verify all required fields are present
        assert hasattr(rate, 'from_currency')
        assert hasattr(rate, 'to_currency')
        assert hasattr(rate, 'rate')
        assert hasattr(rate, 'source')
        assert hasattr(rate, 'fetched_at')
        assert hasattr(rate, 'markup_percentage')
        
        # Verify field types
        assert isinstance(rate.from_currency, str)
        assert isinstance(rate.to_currency, str)
        assert isinstance(rate.rate, Decimal)
        assert isinstance(rate.source, str)
        assert isinstance(rate.fetched_at, datetime)
        assert isinstance(rate.markup_percentage, float)
        
        # Verify reasonable values
        assert len(rate.from_currency) == 3  # Currency codes are 3 letters
        assert len(rate.to_currency) == 3
        assert rate.rate > Decimal("0")
        assert rate.source == "cbr"
        assert 0 <= rate.markup_percentage <= 100  # Reasonable markup range
    
    def test_edge_case_values(self, mock_http_session):
        """Test handling of edge case values in XML."""
        edge_cases = [
            ("0,0000", "zero rate"),
            ("999999,9999", "very high rate"),
            ("0,0001", "very low rate"),
        ]
        
        for rate_value, description in edge_cases:
            xml_template = f'''<?xml version="1.0" encoding="windows-1251"?>
            <ValCurs Date="09.06.2025" name="Foreign Currency Market">
                <Valute ID="R01235">
                    <NumCode>840</NumCode>
                    <CharCode>USD</CharCode>
                    <Nominal>1</Nominal>
                    <Name>Доллар США</Name>
                    <Value>{rate_value}</Value>
                </Valute>
            </ValCurs>'''
            
            mock_http_session.get.return_value.__aenter__.return_value.text.return_value = xml_template
            
            async def run_test():
                rate = await get_rate("USD", "RUB", mock_http_session)
                
                if rate_value == "0,0000":
                    # Zero rate should be rejected
                    assert rate is None, f"Zero rate should be rejected: {description}"
                else:
                    # Non-zero rates should be processed
                    assert rate is not None, f"Valid rate should be processed: {description}"
                    assert rate.rate > Decimal("0"), f"Rate should be positive: {description}"
            
            import asyncio
            asyncio.run(run_test())