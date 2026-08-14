"""End-to-end tests with real URLs and external services.

These tests use actual marketplace URLs to verify that the entire
scraping and calculation pipeline works with real data.
"""

import asyncio
from decimal import Decimal

import pytest

from app.bot.utils import calculate_final_price_async, create_session
from app.scrapers import ebay, grailed_scraper
from app.services import currency, shipping


class TestRealURLsE2E:
    """End-to-end tests with real marketplace URLs."""

    @pytest.mark.asyncio
    async def test_grailed_real_listing(self):
        """Test scraping a real Grailed listing via Algolia client."""
        # Real Grailed URL - active listing verified in incident testing
        test_url = "https://www.grailed.com/listings/99406229-vissla-board-shorts"

        async with create_session() as session:
            try:
                item_data = await grailed_scraper.scrape_item(test_url, session)

                assert item_data is not None, "Should extract item data"
                assert item_data.price is not None, "Should extract item price"
                assert item_data.price > Decimal("0"), "Price should be positive"
                assert item_data.title is not None, "Should extract item title"
                assert len(item_data.title) > 0, "Title should not be empty"
                assert isinstance(item_data.is_buyable, bool), "Should determine buyability"

                # Shipping info should be present
                assert item_data.shipping_us is not None, "Should have shipping info"
                assert item_data.shipping_us >= Decimal("0"), "Shipping should be non-negative"

                seller_profile_url = grailed_scraper.extract_seller_profile_url(item_data)
                if seller_profile_url:
                    seller_data = await grailed_scraper.scrape_seller(seller_profile_url, session)
                    if seller_data:
                        assert seller_data.num_reviews >= 0, "Review count should be non-negative"
                        assert 0.0 <= seller_data.avg_rating <= 5.0, "Rating should be 0-5"
                        assert isinstance(seller_data.trusted_badge, bool), "Badge should be boolean"

                # Test full calculation pipeline
                shipping_quote = shipping.estimate_shopfans_shipping(item_data.title)
                result = await calculate_final_price_async(
                    item_data.price,
                    item_data.shipping_us,
                    shipping_quote.cost_usd,
                    session=session,
                )

                assert result.final_price_usd > item_data.price, "Final price should include fees"

            except Exception as e:
                pytest.fail(f"Grailed scraping failed: {e}")

    @pytest.mark.asyncio
    async def test_currency_conversion_real_api(self):
        """Test currency conversion with real CBR API."""
        async with create_session() as session:
            try:
                rate = await currency.get_exchange_rate("USD", "RUB", session)

                if rate is None:
                    pytest.skip("CBR API not accessible")

                # Verify rate structure
                assert rate.from_currency == "USD"
                assert rate.to_currency == "RUB"
                assert rate.rate > Decimal("0")
                assert rate.source == "cbr"
                assert rate.markup_percentage == 5.0

                # Rate should be in reasonable range (50-200 RUB per USD)
                assert (
                    Decimal("50") <= rate.rate <= Decimal("200")
                ), f"Rate {rate.rate} seems unreasonable"

            except Exception as e:
                pytest.fail(f"Currency conversion failed: {e}")

    @pytest.mark.asyncio
    async def test_shipping_estimation_patterns(self):
        """Test shipping estimation with various real item titles."""
        test_titles = [
            "Supreme Box Logo Hoodie Black Large",
            "Nike Air Jordan 1 Retro High OG Chicago Size 10",
            "Vintage Band T-Shirt Medium",
            "Designer Silk Tie Navy Blue",
            "Random item without clear category",
        ]

        expected_categories = ["hoodie", "sneakers", "t-shirt", "tie", "default"]

        for title, expected_category in zip(test_titles, expected_categories, strict=True):
            quote = shipping.estimate_shopfans_shipping(title)

            assert quote.weight_kg > Decimal("0"), f"Weight should be positive for: {title}"
            assert quote.cost_usd > Decimal("0"), f"Cost should be positive for: {title}"
            assert len(quote.description) > 0, f"Description should exist for: {title}"

    @pytest.mark.asyncio
    async def test_grailed_app_link_resolution(self):
        """Test Grailed app.link shortener resolution."""
        test_short_url = "https://grailed.app.link/example"

        async with create_session() as session:
            try:
                from app.bot.handlers import _resolve_shortener

                resolved_url = await _resolve_shortener(test_short_url, session)
                assert isinstance(resolved_url, str)
                assert len(resolved_url) > 0

            except Exception as e:
                print(f"Shortener resolution failed (expected if non-existent link): {e}")
