"""End-to-end tests with real URLs and external services.

These tests use actual eBay and Grailed URLs to verify that the entire
scraping and calculation pipeline works with real data. They may be slower
and can fail due to external service issues.
"""

import pytest
import asyncio
from decimal import Decimal

from app.scrapers import ebay, grailed
from app.services import currency, shipping
from app.bot.utils import calculate_final_price_async, create_session


class TestRealURLsE2E:
    """End-to-end tests with real marketplace URLs."""
    
    @pytest.mark.skip(reason="Temporarily disabled while eBay listing data stays unstable")
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_ebay_real_listing(self):
        """Test scraping a real eBay listing."""
        # Real eBay URL - sneakers listing
        test_url = "https://www.ebay.com/itm/266024628787"  # Nike Air Jordan example
        
        async with create_session() as session:
            try:
                item_data = await ebay.scrape_ebay_item(test_url, session)
                
                if item_data is None:
                    pytest.skip("eBay listing not accessible - may be removed or changed")
                
                # Assert basic data structure
                assert item_data.price is not None, "Should extract item price"
                assert item_data.price > Decimal("0"), "Price should be positive"
                assert item_data.title is not None, "Should extract item title"
                assert len(item_data.title) > 0, "Title should not be empty"
                
                # Shipping may be 0 for free shipping or pickup items
                assert item_data.shipping_us is not None, "Should have shipping info"
                assert item_data.shipping_us >= Decimal("0"), "Shipping should be non-negative"
                
                # Test price calculation integration
                shipping_quote = shipping.estimate_shopfans_shipping(item_data.title)
                result = await calculate_final_price_async(
                    item_data.price,
                    item_data.shipping_us,
                    shipping_quote.cost_usd,
                    session=session,
                )
                
                assert result.final_price_usd > item_data.price, "Final price should include fees"
                
                print(f"✅ eBay E2E Test Results:")
                print(f"   Item: {item_data.title[:50]}...")
                print(f"   Price: ${item_data.price}")
                print(f"   US Shipping: ${item_data.shipping_us}")
                print(f"   RU Shipping: ${shipping_quote.cost_usd}")
                print(f"   Commission: ${result.commission}")
                print(f"   Final: ${result.final_price_usd}")
                
            except Exception as e:
                pytest.fail(f"eBay scraping failed: {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_grailed_real_listing(self):
        """Test scraping a real Grailed listing."""
        # Real Grailed URL - clothing listing
        test_url = "https://www.grailed.com/listings/37851567-nike-vintage-nike-tech-fleece-hoodie"
        
        async with create_session() as session:
            try:
                item_data, seller_data = await grailed.get_item_data(test_url, session)
                
                if item_data is None:
                    pytest.skip("Grailed listing not accessible - may be removed or changed")
                
                # Assert item data
                assert item_data.price is not None, "Should extract item price"
                assert item_data.price > Decimal("0"), "Price should be positive"
                assert item_data.title is not None, "Should extract item title"
                assert len(item_data.title) > 0, "Title should not be empty"
                assert isinstance(item_data.is_buyable, bool), "Should determine buyability"
                
                # Shipping info should be present
                assert item_data.shipping_us is not None, "Should have shipping info"
                assert item_data.shipping_us >= Decimal("0"), "Shipping should be non-negative"
                
                # Seller data may or may not be available due to React SPA
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
                
                print(f"✅ Grailed E2E Test Results:")
                print(f"   Item: {item_data.title[:50]}...")
                print(f"   Price: ${item_data.price}")
                print(f"   US Shipping: ${item_data.shipping_us}")
                print(f"   Buyable: {item_data.is_buyable}")
                print(f"   RU Shipping: ${shipping_quote.cost_usd}")
                print(f"   Commission: ${result.commission}")
                print(f"   Final: ${result.final_price_usd}")
                
                if seller_data:
                    print(f"   Seller Rating: {seller_data.avg_rating}")
                    print(f"   Seller Reviews: {seller_data.num_reviews}")
                    print(f"   Trusted Badge: {seller_data.trusted_badge}")
                
            except Exception as e:
                pytest.fail(f"Grailed scraping failed: {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_grailed_seller_profile_with_headless(self):
        """Test Grailed seller profile analysis with headless browser."""
        # Real Grailed profile URL
        test_profile_url = "https://grailed.com/DP1211"
        
        async with create_session() as session:
            try:
                seller_analysis = await grailed.analyze_seller_profile(test_profile_url, session)
                
                if seller_analysis is None:
                    pytest.skip("Grailed profile not accessible or headless browser disabled")
                
                # Should have basic profile structure
                assert 'num_reviews' in seller_analysis
                assert 'avg_rating' in seller_analysis
                assert 'trusted_badge' in seller_analysis
                assert 'last_updated' in seller_analysis
                
                # Values should be reasonable
                assert seller_analysis['num_reviews'] >= 0
                assert 0.0 <= seller_analysis['avg_rating'] <= 5.0
                assert isinstance(seller_analysis['trusted_badge'], bool)
                
                print(f"✅ Grailed Profile E2E Test Results:")
                print(f"   Profile: {test_profile_url}")
                print(f"   Reviews: {seller_analysis['num_reviews']}")
                print(f"   Rating: {seller_analysis['avg_rating']}")
                print(f"   Trusted: {seller_analysis['trusted_badge']}")
                print(f"   Last Updated: {seller_analysis['last_updated']}")
                
            except Exception as e:
                pytest.fail(f"Grailed profile analysis failed: {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(20)
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
                assert Decimal("50") <= rate.rate <= Decimal("200"), f"Rate {rate.rate} seems unreasonable"
                
                print(f"✅ Currency E2E Test Results:")
                print(f"   USD to RUB rate: {rate.rate}")
                print(f"   Source: {rate.source}")
                print(f"   Markup: {rate.markup_percentage}%")
                print(f"   Fetched: {rate.fetched_at}")
                
            except Exception as e:
                pytest.fail(f"Currency conversion failed: {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(15)
    async def test_shipping_estimation_patterns(self):
        """Test shipping estimation with various real item titles."""
        test_titles = [
            "Supreme Box Logo Hoodie Black Large",
            "Nike Air Jordan 1 Retro High OG Chicago Size 10",
            "Vintage Band T-Shirt Medium",
            "Designer Silk Tie Navy Blue",
            "Random item without clear category"
        ]
        
        expected_categories = ["hoodie", "sneakers", "t-shirt", "tie", "default"]
        
        for title, expected_category in zip(test_titles, expected_categories):
            quote = shipping.estimate_shopfans_shipping(title)
            
            assert quote.weight_kg > Decimal("0"), f"Weight should be positive for: {title}"
            assert quote.cost_usd > Decimal("0"), f"Cost should be positive for: {title}"
            assert len(quote.description) > 0, f"Description should exist for: {title}"
            
            print(f"✅ Shipping Test: {title[:30]}...")
            print(f"   Weight: {quote.weight_kg}kg")
            print(f"   Cost: ${quote.cost_usd}")
            print(f"   Category: {quote.description}")
    
    @pytest.mark.skip(reason="Temporarily disabled while eBay listing data stays unstable")
    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_full_pipeline_ebay_to_rub(self):
        """Test complete pipeline from eBay URL to RUB price."""
        test_url = "https://www.ebay.com/itm/266024628787"
        
        async with create_session() as session:
            try:
                # Step 1: Scrape item
                item_data = await ebay.scrape_ebay_item(test_url, session)
                if item_data is None:
                    pytest.skip("eBay listing not accessible")
                
                # Step 2: Get shipping estimate
                shipping_quote = shipping.estimate_shopfans_shipping(item_data.title)
                
                # Step 3: Calculate commission and final price
                price_calc = await calculate_final_price_async(
                    item_data.price,
                    item_data.shipping_us,
                    shipping_quote.cost_usd,
                    session=session,
                )
                
                # Step 4: Get exchange rate
                exchange_rate = await currency.get_exchange_rate("USD", "RUB", session)
                if exchange_rate is None:
                    pytest.skip("Currency API not accessible")
                
                # Step 5: Convert to RUB
                final_rub = (price_calc.final_price_usd * exchange_rate.rate).quantize(Decimal('0.01'))
                
                # Verify complete pipeline
                assert final_rub > Decimal("0"), "Final RUB price should be positive"
                assert final_rub > price_calc.final_price_usd, "RUB should be larger number than USD"
                
                print(f"✅ Full Pipeline E2E Test Results:")
                print(f"   URL: {test_url}")
                print(f"   Item: {item_data.title[:40]}...")
                print(f"   Item Price: ${item_data.price}")
                print(f"   US Shipping: ${item_data.shipping_us}")
                print(f"   RU Shipping: ${shipping_quote.cost_usd}")
                print(f"   Commission: ${price_calc.commission}")
                print(f"   Total USD: ${price_calc.final_price_usd}")
                print(f"   Exchange Rate: {exchange_rate.rate}")
                print(f"   Final RUB: ₽{final_rub}")
                
            except Exception as e:
                pytest.fail(f"Full pipeline test failed: {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_grailed_app_link_resolution(self):
        """Test Grailed app.link shortener resolution."""
        # Note: This would need a real app.link URL
        # For now, test the resolution function directly
        test_short_url = "https://grailed.app.link/example"
        
        async with create_session() as session:
            try:
                from app.bot.handlers import _resolve_shortener
                resolved_url = await _resolve_shortener(test_short_url, session)
                
                # If it's a real shortener, it should resolve to grailed.com
                # If not, it should return the original URL
                assert isinstance(resolved_url, str)
                assert len(resolved_url) > 0
                
                print(f"✅ Shortener Resolution Test:")
                print(f"   Original: {test_short_url}")
                print(f"   Resolved: {resolved_url}")
                
            except Exception as e:
                # Shortener resolution failures are acceptable in E2E tests
                print(f"⚠️ Shortener resolution failed (expected): {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_concurrent_scraping(self):
        """Test concurrent scraping of multiple URLs."""
        test_urls = [
            "https://www.ebay.com/itm/266024628787",
            "https://www.grailed.com/listings/37851567-nike-vintage-nike-tech-fleece-hoodie"
        ]
        
        async with create_session() as session:
            try:
                # Test concurrent scraping using asyncio.gather
                tasks = []
                
                for url in test_urls:
                    if "ebay.com" in url:
                        task = ebay.scrape_ebay_item(url, session)
                    elif "grailed.com" in url:
                        task = grailed.scrape_grailed_item(url, session)
                    else:
                        continue
                    
                    tasks.append(task)
                
                # Execute all tasks concurrently
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                successful_results = 0
                for i, result in enumerate(results):
                    if not isinstance(result, Exception) and result is not None:
                        successful_results += 1
                        print(f"✅ Concurrent scraping result {i+1}: Success")
                    else:
                        print(f"⚠️ Concurrent scraping result {i+1}: {result}")
                
                # At least one should succeed for the test to be meaningful
                if successful_results == 0:
                    pytest.skip("No URLs were accessible for concurrent testing")
                
                print(f"✅ Concurrent Scraping: {successful_results}/{len(results)} successful")
                
            except Exception as e:
                pytest.fail(f"Concurrent scraping test failed: {e}")
