"""Integration tests for bot handlers.

Tests the interaction between handlers, scrapers, and business logic
with mocked external dependencies but real internal component interactions.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal

from app.bot.handlers import handle_link, _handle_listings, _handle_seller_profile
from app.models import ItemData, SellerData


class TestBotHandlerIntegration:
    """Test bot handlers with component integration."""
    
    @pytest.mark.asyncio
    async def test_handle_listing_full_flow(self, mock_config, mock_http_session, sample_item_data, sample_exchange_rate):
        """Test complete listing handling flow with mocked dependencies."""
        # Setup mocks
        update = AsyncMock()
        update.message.text = "https://www.ebay.com/itm/123456789"
        update.message.reply_text = AsyncMock()
        
        context = AsyncMock()
        
        # Mock the scraping functions
        with patch('app.scrapers.ebay.scrape_ebay_item') as mock_ebay_scrape, \
             patch('app.services.currency.get_exchange_rate') as mock_exchange, \
             patch('app.services.shipping.estimate_shopfans_shipping') as mock_shipping:
            
            # Setup return values
            mock_ebay_scrape.return_value = sample_item_data['ebay_item']
            mock_exchange.return_value = sample_exchange_rate
            
            # Mock shipping estimation
            from app.models import ShippingQuote
            mock_shipping.return_value = ShippingQuote(
                weight_kg=Decimal("0.80"),
                cost_usd=Decimal("25.00"),
                description="Test shipping"
            )
            
            # Act
            await handle_link(update, context)
            
            # Assert
            mock_ebay_scrape.assert_called_once()
            mock_exchange.assert_called_once_with("USD", "RUB", mock_http_session)
            update.message.reply_text.assert_called()
            
            # Verify the response contains expected elements
            response_text = update.message.reply_text.call_args[1]['text']
            assert "💰 Расчёт стоимости" in response_text
            assert "$89.99" in response_text  # Item price
            assert "$12.50" in response_text  # US shipping
    
    @pytest.mark.asyncio
    async def test_handle_grailed_listing_with_seller_analysis(self, mock_config, mock_http_session, sample_item_data, sample_seller_data):
        """Test Grailed listing handling with seller reliability analysis."""
        update = AsyncMock()
        update.message.text = "https://www.grailed.com/listings/123456-supreme-hoodie"
        update.message.reply_text = AsyncMock()
        context = AsyncMock()
        
        with patch('app.scrapers.grailed.scrape_grailed_item') as mock_grailed_scrape, \
             patch('app.services.currency.get_exchange_rate') as mock_exchange, \
             patch('app.services.shipping.estimate_shopfans_shipping') as mock_shipping:
            
            # Setup Grailed item with seller data
            grailed_item = sample_item_data['grailed_item']
            seller_data = sample_seller_data['excellent_seller']
            
            mock_grailed_scrape.return_value = (grailed_item, seller_data)
            mock_exchange.return_value = None  # No exchange rate for this test
            
            from app.models import ShippingQuote
            mock_shipping.return_value = ShippingQuote(
                weight_kg=Decimal("0.80"),
                cost_usd=Decimal("25.00"),
                description="Hoodie shipping"
            )
            
            # Act
            await handle_link(update, context)
            
            # Assert seller analysis is included
            response_text = update.message.reply_text.call_args[1]['text']
            assert "💎 Diamond" in response_text  # Should show excellent seller rating
            assert "95" in response_text  # Should show high score
    
    @pytest.mark.asyncio
    async def test_handle_multiple_urls(self, mock_config, mock_http_session, sample_item_data):
        """Test handling message with multiple URLs."""
        update = AsyncMock()
        update.message.text = """Check these items:
        https://www.ebay.com/itm/123456789
        https://www.grailed.com/listings/123456-supreme-hoodie
        """
        update.message.reply_text = AsyncMock()
        context = AsyncMock()
        
        with patch('app.scrapers.ebay.scrape_ebay_item') as mock_ebay, \
             patch('app.scrapers.grailed.scrape_grailed_item') as mock_grailed, \
             patch('app.services.currency.get_exchange_rate') as mock_exchange, \
             patch('app.services.shipping.estimate_shopfans_shipping') as mock_shipping:
            
            # Setup return values
            mock_ebay.return_value = sample_item_data['ebay_item']
            mock_grailed.return_value = (sample_item_data['grailed_item'], None)
            mock_exchange.return_value = None
            
            from app.models import ShippingQuote
            mock_shipping.return_value = ShippingQuote(
                weight_kg=Decimal("0.60"),
                cost_usd=Decimal("25.00"),
                description="Default shipping"
            )
            
            # Act
            await handle_link(update, context)
            
            # Assert both scrapers were called
            mock_ebay.assert_called_once()
            mock_grailed.assert_called_once()
            
            # Should have multiple reply messages
            assert update.message.reply_text.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_handle_seller_profile_analysis(self, mock_config, mock_http_session, sample_seller_data):
        """Test seller profile analysis flow."""
        update = AsyncMock()
        update.message.text = "https://grailed.com/username"
        update.message.reply_text = AsyncMock()
        update.message.delete = AsyncMock()
        context = AsyncMock()
        
        # Mock loading message
        loading_message = AsyncMock()
        loading_message.delete = AsyncMock()
        update.message.reply_text.return_value = loading_message
        
        with patch('app.scrapers.grailed.analyze_seller_profile') as mock_analyze:
            # Setup seller analysis return
            seller_analysis = {
                'num_reviews': 150,
                'avg_rating': 4.8,
                'trusted_badge': True,
                'last_updated': sample_seller_data['excellent_seller'].last_updated,
                'reliability': None  # Will be calculated
            }
            mock_analyze.return_value = seller_analysis
            
            # Act
            await handle_link(update, context)
            
            # Assert
            mock_analyze.assert_called_once()
            loading_message.delete.assert_called_once()
            
            # Should send seller analysis response
            final_response = update.message.reply_text.call_args_list[-1][1]['text']
            assert "Анализ продавца Grailed" in final_response
            assert "💎 Diamond" in final_response  # Excellent seller
    
    @pytest.mark.asyncio
    async def test_handle_offer_only_item(self, mock_config, mock_http_session):
        """Test handling of offer-only items (not buyable)."""
        update = AsyncMock()
        update.message.text = "https://www.grailed.com/listings/123456-offer-only"
        update.message.reply_text = AsyncMock()
        context = AsyncMock()
        
        with patch('app.scrapers.grailed.scrape_grailed_item') as mock_grailed:
            # Setup offer-only item
            from app.models import ItemData
            offer_only_item = ItemData(
                price=Decimal("150.00"),
                shipping_us=Decimal("20.00"),
                is_buyable=False,  # Not buyable
                title="Supreme Hoodie (Offers Only)"
            )
            mock_grailed.return_value = (offer_only_item, None)
            
            # Act
            await handle_link(update, context)
            
            # Assert
            response_text = update.message.reply_text.call_args[1]['text']
            assert "не имеет фиксированной цены" in response_text.lower()
            assert "$150.00" in response_text  # Should still show price for reference
    
    @pytest.mark.asyncio
    async def test_handle_scraping_failure(self, mock_config, mock_http_session):
        """Test handling when scraping fails."""
        update = AsyncMock()
        update.message.text = "https://www.ebay.com/itm/invalid"
        update.message.reply_text = AsyncMock()
        context = AsyncMock()
        
        with patch('app.scrapers.ebay.scrape_ebay_item') as mock_ebay:
            # Setup scraping failure
            mock_ebay.return_value = None
            
            # Act
            await handle_link(update, context)
            
            # Assert error handling
            # The handler should gracefully handle the failure
            # and may send an error message or skip the item
            mock_ebay.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_commission_calculation_integration(self, mock_config, mock_http_session):
        """Test that commission calculation is properly integrated."""
        update = AsyncMock()
        update.message.text = "https://www.ebay.com/itm/123456789"
        update.message.reply_text = AsyncMock()
        context = AsyncMock()
        
        with patch('app.scrapers.ebay.scrape_ebay_item') as mock_ebay, \
             patch('app.services.shipping.estimate_shopfans_shipping') as mock_shipping:
            
            # Setup item that should trigger percentage commission
            from app.models import ItemData, ShippingQuote
            high_value_item = ItemData(
                price=Decimal("120.00"),
                shipping_us=Decimal("40.00"),  # Total $160, above $150 threshold
                is_buyable=True,
                title="High value item"
            )
            mock_ebay.return_value = high_value_item
            
            mock_shipping.return_value = ShippingQuote(
                weight_kg=Decimal("1.0"),
                cost_usd=Decimal("25.00"),
                description="Standard shipping"
            )
            
            # Act
            await handle_link(update, context)
            
            # Assert commission is calculated correctly
            response_text = update.message.reply_text.call_args[1]['text']
            assert "$16.00" in response_text  # (120 + 40) * 0.10 = 16.00
            assert "10%" in response_text     # Should indicate percentage commission
    
    @pytest.mark.asyncio
    async def test_currency_conversion_integration(self, mock_config, mock_http_session, sample_exchange_rate):
        """Test currency conversion integration in the flow."""
        update = AsyncMock()
        update.message.text = "https://www.ebay.com/itm/123456789"
        update.message.reply_text = AsyncMock()
        context = AsyncMock()
        
        with patch('app.scrapers.ebay.scrape_ebay_item') as mock_ebay, \
             patch('app.services.currency.get_exchange_rate') as mock_exchange, \
             patch('app.services.shipping.estimate_shopfans_shipping') as mock_shipping:
            
            from app.models import ItemData, ShippingQuote
            test_item = ItemData(
                price=Decimal("100.00"),
                shipping_us=Decimal("10.00"),
                is_buyable=True,
                title="Test item"
            )
            mock_ebay.return_value = test_item
            mock_exchange.return_value = sample_exchange_rate
            
            mock_shipping.return_value = ShippingQuote(
                weight_kg=Decimal("0.5"),
                cost_usd=Decimal("20.00"),
                description="Test shipping"
            )
            
            # Act
            await handle_link(update, context)
            
            # Assert
            response_text = update.message.reply_text.call_args[1]['text']
            assert "₽" in response_text  # Should contain ruble conversion
            
            # Calculate expected conversion: (100 + 10 + 20 + 15) * 95.50 = 13,847.50
            assert "₽13,847.50" in response_text or "₽13 847.50" in response_text