"""Integration tests for bot handlers with mocked orchestration layers."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers import handle_link
from app.bot.response_formatter import response_formatter
from app.bot.scraping_orchestrator import scraping_orchestrator
from app.bot.types import ItemScrapeResult, SellerScrapeResult
from app.models import ItemData, SellerData


class TestBotHandlerIntegration:
    """Test bot handlers with component integration."""
    
    @pytest.mark.asyncio
    async def test_handle_listing_full_flow(
        self, mock_config, mock_http_session, sample_item_data, sample_exchange_rate
    ):
        """Test complete listing handling flow with mocked orchestration."""
        url = "https://www.ebay.com/itm/123456789"
        update = AsyncMock()
        update.message.text = url
        update.message.reply_text = AsyncMock()
        update.message.reply_photo = AsyncMock()
        update.effective_user = MagicMock(id=12345, username="test_user")
        context = AsyncMock()
        context.application = MagicMock()
        context.application.bot = MagicMock()

        item_result: ItemScrapeResult = {
            "success": True,
            "platform": "ebay",
            "url": url,
            "item_data": sample_item_data["ebay_item"],
            "seller_data": None,
            "error": None,
            "processing_time_ms": 120,
        }

        expected_response = "💰 Итог по товару: $89.99 + $12.50"

        with patch.object(
            scraping_orchestrator,
            "process_urls_concurrent",
            AsyncMock(return_value=[item_result]),
        ) as mock_process, patch.object(
            response_formatter,
            "format_item_response",
            AsyncMock(return_value=expected_response),
        ):
            await handle_link(update, context)

        mock_process.assert_awaited_once_with(
            [url], update.effective_user.id, update.effective_user.username
        )

        # Последний ответ пользователю содержит рассчитанные данные
        final_call = update.message.reply_text.await_args_list[-1]
        final_text = final_call.kwargs.get("text") if "text" in final_call.kwargs else final_call.args[0]
        assert expected_response in final_text
    
    @pytest.mark.asyncio
    async def test_handle_grailed_listing_with_seller_analysis(self, mock_config, mock_http_session, sample_item_data, sample_seller_data):
        """Test Grailed listing handling with seller reliability analysis."""
        url = "https://www.grailed.com/listings/123456-supreme-hoodie"
        update = AsyncMock()
        update.message.text = url
        update.message.reply_text = AsyncMock()
        update.message.reply_photo = AsyncMock()
        update.effective_user = MagicMock(id=98765, username="grailed_tester")
        context = AsyncMock()
        context.application = MagicMock()
        context.application.bot = MagicMock()

        grailed_item = sample_item_data["grailed_item"]
        seller_data = sample_seller_data["excellent_seller"]
        item_result: ItemScrapeResult = {
            "success": True,
            "platform": "grailed",
            "url": url,
            "item_data": grailed_item,
            "seller_data": seller_data,
            "error": None,
            "processing_time_ms": 150,
        }

        expected_response = "💎 Diamond seller rating included"

        with patch.object(
            scraping_orchestrator,
            "process_urls_concurrent",
            AsyncMock(return_value=[item_result]),
        ), patch.object(
            response_formatter,
            "format_item_response",
            AsyncMock(return_value=expected_response),
        ):
            await handle_link(update, context)

        final_call = update.message.reply_text.await_args_list[-1]
        final_text = final_call.kwargs.get("text") if "text" in final_call.kwargs else final_call.args[0]
        assert "💎 Diamond" in final_text
    
    @pytest.mark.asyncio
    async def test_handle_multiple_urls(self, mock_config, mock_http_session, sample_item_data):
        """Test handling message with multiple URLs."""
        text_with_urls = """Check these items:
        https://www.ebay.com/itm/123456789
        https://www.grailed.com/listings/123456-supreme-hoodie
        """
        update = AsyncMock()
        update.message.text = text_with_urls
        update.message.reply_text = AsyncMock()
        update.message.reply_photo = AsyncMock()
        update.effective_user = MagicMock(id=222, username="multi_user")
        context = AsyncMock()
        context.application = MagicMock()
        context.application.bot = MagicMock()

        ebay_result: ItemScrapeResult = {
            "success": True,
            "platform": "ebay",
            "url": "https://www.ebay.com/itm/123456789",
            "item_data": sample_item_data["ebay_item"],
            "seller_data": None,
            "error": None,
            "processing_time_ms": 80,
        }
        grailed_result: ItemScrapeResult = {
            "success": True,
            "platform": "grailed",
            "url": "https://www.grailed.com/listings/123456-supreme-hoodie",
            "item_data": sample_item_data["grailed_item"],
            "seller_data": None,
            "error": None,
            "processing_time_ms": 95,
        }

        responses = ["Ответ по eBay", "Ответ по Grailed"]

        with patch.object(
            scraping_orchestrator,
            "process_urls_concurrent",
            AsyncMock(return_value=[ebay_result, grailed_result]),
        ), patch.object(
            response_formatter,
            "format_item_response",
            AsyncMock(side_effect=responses),
        ):
            await handle_link(update, context)

        # Должны отправить два ответа (по одному на ссылку)
        assert len(update.message.reply_text.await_args_list) >= 3  # 1 загрузка + 2 результата
        sent_texts = []
        for call in update.message.reply_text.await_args_list:
            if call.kwargs.get("text"):
                sent_texts.append(call.kwargs["text"])
            elif call.args:
                sent_texts.append(call.args[0])
        assert any("Ответ по eBay" in text for text in sent_texts)
        assert any("Ответ по Grailed" in text for text in sent_texts)
    
    @pytest.mark.asyncio
    async def test_handle_seller_profile_analysis(self, mock_config, mock_http_session, sample_seller_data):
        """Test seller profile analysis flow."""
        update = AsyncMock()
        update.message.text = "https://grailed.com/username"
        update.message.reply_text = AsyncMock()
        update.message.reply_photo = AsyncMock()
        update.effective_user = MagicMock(id=333, username="profile_user")
        context = AsyncMock()
        context.application = MagicMock()
        context.application.bot = MagicMock()

        loading_message = AsyncMock()
        update.message.reply_text.return_value = loading_message

        seller_result: SellerScrapeResult = {
            "success": True,
            "platform": "profile",
            "url": "https://grailed.com/username",
            "seller_data": sample_seller_data["excellent_seller"],
            "reliability_score": MagicMock(category="Diamond", total_score=95),
            "error": None,
            "processing_time_ms": 110,
        }

        expected_profile_response = "Анализ продавца Grailed: 💎 Diamond"

        with patch.object(
            scraping_orchestrator,
            "process_urls_concurrent",
            AsyncMock(return_value=[seller_result]),
        ), patch.object(
            response_formatter,
            "format_seller_profile_response",
            MagicMock(return_value=expected_profile_response),
        ):
            await handle_link(update, context)

        loading_message.edit_text.assert_awaited()
        edit_call = loading_message.edit_text.await_args_list[-1]
        edit_text = edit_call.kwargs.get("text") if "text" in edit_call.kwargs else edit_call.args[0]
        assert "Анализ продавца Grailed" in edit_text
    
    @pytest.mark.asyncio
    async def test_handle_offer_only_item(self, mock_config, mock_http_session):
        """Test handling of offer-only items (not buyable)."""
        update = AsyncMock()
        update.message.text = "https://www.grailed.com/listings/123456-offer-only"
        update.message.reply_text = AsyncMock()
        update.message.reply_photo = AsyncMock()
        update.effective_user = MagicMock(id=444, username="offer_only_user")
        context = AsyncMock()
        context.application = MagicMock()
        context.application.bot = MagicMock()
        
        offer_only_item = ItemData(
            price=Decimal("150.00"),
            shipping_us=Decimal("20.00"),
            is_buyable=False,
            title="Supreme Hoodie (Offers Only)",
        )
        item_result: ItemScrapeResult = {
            "success": True,
            "platform": "grailed",
            "url": update.message.text,
            "item_data": offer_only_item,
            "seller_data": None,
            "error": None,
            "processing_time_ms": 60,
        }

        expected_text = "не имеет фиксированной цены"

        with patch.object(
            scraping_orchestrator,
            "process_urls_concurrent",
            AsyncMock(return_value=[item_result]),
        ), patch.object(
            response_formatter,
            "format_item_response",
            AsyncMock(return_value=f"Товар {expected_text}: $150.00"),
        ):
            await handle_link(update, context)

        final_call = update.message.reply_text.await_args_list[-1]
        final_text = final_call.kwargs.get("text") if "text" in final_call.kwargs else final_call.args[0]
        assert expected_text in final_text.lower()
        assert "$150.00" in final_text
    
    @pytest.mark.asyncio
    async def test_handle_scraping_failure(self, mock_config, mock_http_session):
        """Test handling when scraping fails."""
        update = AsyncMock()
        update.message.text = "https://www.ebay.com/itm/invalid"
        update.message.reply_text = AsyncMock()
        update.message.reply_photo = AsyncMock()
        update.effective_user = MagicMock(id=555, username="failure_user")
        context = AsyncMock()
        context.application = MagicMock()
        context.application.bot = MagicMock()

        failure_result: ItemScrapeResult = {
            "success": False,
            "platform": "ebay",
            "url": update.message.text,
            "error": "Network timeout",
            "processing_time_ms": 0,
        }
        failure_text = "❌ Ошибка при обработке ссылки"

        with patch.object(
            scraping_orchestrator,
            "process_urls_concurrent",
            AsyncMock(return_value=[failure_result]),
        ), patch.object(
            response_formatter,
            "format_item_response",
            AsyncMock(return_value=failure_text),
        ):
            await handle_link(update, context)

        final_call = update.message.reply_text.await_args_list[-1]
        final_text = final_call.kwargs.get("text") if "text" in final_call.kwargs else final_call.args[0]
        assert failure_text in final_text
    
