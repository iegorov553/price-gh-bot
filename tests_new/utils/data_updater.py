"""Automated test data updater.

Utilities to keep test expectations in sync with real data from external
services. Helps prevent test failures due to outdated expectations.
"""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.bot.utils import create_session
from app.scrapers import ebay, grailed
from app.services.currency import get_exchange_rate
from app.services.shipping import estimate_shopfans_shipping


class TestDataUpdater:
    """Updates test fixtures with current real data."""

    def __init__(self, fixtures_path: Path = None):
        """Initialize with fixtures directory path."""
        if fixtures_path is None:
            fixtures_path = Path(__file__).parent.parent / "fixtures"
        self.fixtures_path = fixtures_path
        self.test_data_file = fixtures_path / "test_data.json"

    def load_test_data(self) -> dict[str, Any]:
        """Load current test data."""
        if self.test_data_file.exists():
            with open(self.test_data_file) as f:
                return json.load(f)
        return {}

    def save_test_data(self, data: dict[str, Any]) -> None:
        """Save updated test data."""
        data["last_updated"] = datetime.now(UTC).isoformat()

        # Ensure directory exists
        self.fixtures_path.mkdir(parents=True, exist_ok=True)

        with open(self.test_data_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    async def update_shipping_expectations(self) -> None:
        """Update shipping cost expectations based on current calculations."""
        print("🚢 Updating shipping expectations...")

        test_items = [
            "Supreme hoodie black large",
            "Nike Air Jordan 1 sneakers size 10",
            "Vintage band t-shirt",
            "Silk tie navy blue",
            "Random unknown item type",
        ]

        updated_expectations = {}

        for item in test_items:
            try:
                quote = estimate_shopfans_shipping(item)
                updated_expectations[item] = {
                    "weight": float(quote.weight_kg),
                    "cost": float(quote.cost_usd),
                    "cost_range": [float(quote.cost_usd) - 2, float(quote.cost_usd) + 2],
                    "description": quote.description,
                    "updated": datetime.now(UTC).isoformat(),
                }
                print(f"  ✅ {item}: {quote.weight_kg}kg, ${quote.cost_usd}")
            except Exception as e:
                print(f"  ❌ {item}: Failed - {e}")

        # Update test data
        test_data = self.load_test_data()
        test_data["shipping_expectations"] = updated_expectations
        self.save_test_data(test_data)

        print(f"📦 Updated {len(updated_expectations)} shipping expectations")

    async def update_currency_ranges(self) -> None:
        """Update expected currency rate ranges."""
        print("💱 Updating currency rate expectations...")

        async with create_session() as session:
            try:
                rate = await get_exchange_rate("USD", "RUB", session)

                if rate:
                    current_rate = float(rate.rate)

                    # Set reasonable range around current rate (±20%)
                    rate_range = {
                        "min": max(50, current_rate * 0.8),
                        "max": min(200, current_rate * 1.2),
                        "current": current_rate,
                        "markup_percentage": rate.markup_percentage,
                        "updated": datetime.now(UTC).isoformat(),
                    }

                    test_data = self.load_test_data()
                    test_data["currency_rates"] = rate_range
                    self.save_test_data(test_data)

                    print(f"  ✅ Current rate: {current_rate} RUB/USD")
                    print(f"  📊 Range: {rate_range['min']:.1f} - {rate_range['max']:.1f}")
                else:
                    print("  ❌ Failed to fetch current rate")

            except Exception as e:
                print(f"  ❌ Currency update failed: {e}")

    async def verify_test_urls(self) -> None:
        """Verify that test URLs are still accessible."""
        print("🔗 Verifying test URLs...")

        test_data = self.load_test_data()
        urls_to_check = []

        # Collect URLs from test data
        for platform in ["ebay", "grailed"]:
            if platform in test_data.get("test_urls", {}):
                urls_to_check.extend(test_data["test_urls"][platform])

        async with create_session() as session:
            for url_data in urls_to_check:
                url = url_data["url"]
                try:
                    if "ebay.com" in url:
                        result = await ebay.scrape_ebay_item(url, session)
                    elif "grailed.com" in url:
                        result = await grailed.scrape_grailed_item(url, session)
                    else:
                        continue

                    if result:
                        url_data["last_verified"] = datetime.now(UTC).date().isoformat()
                        url_data["status"] = "accessible"
                        print(f"  ✅ {url[:50]}... - Accessible")
                    else:
                        url_data["status"] = "inaccessible"
                        print(f"  ❌ {url[:50]}... - Not accessible")

                except Exception as e:
                    url_data["status"] = "error"
                    url_data["error"] = str(e)
                    print(f"  ⚠️ {url[:50]}... - Error: {e}")

        self.save_test_data(test_data)
        print("🔍 URL verification complete")

    async def update_commission_examples(self) -> None:
        """Update commission calculation examples."""
        print("💰 Updating commission examples...")

        from app.bot.utils import calculate_final_price

        test_cases = [
            (80, 20, "Below threshold with shipping"),
            (120, 40, "Above threshold due to shipping"),
            (200, 50, "High value with high shipping"),
            (150, 0, "Exactly at threshold"),
            (100, 50, "Low item, high shipping above threshold"),
        ]

        updated_examples = []

        for item_price, us_shipping, description in test_cases:
            try:
                result = calculate_final_price(
                    Decimal(str(item_price)),
                    Decimal(str(us_shipping)),
                    Decimal("25.00"),  # Standard RU shipping
                )

                commission_base = item_price + us_shipping
                commission_type = "fixed" if commission_base < 150 else "percentage"

                example = {
                    "item_price": item_price,
                    "us_shipping": us_shipping,
                    "ru_shipping": 25.00,
                    "commission_base": commission_base,
                    "expected_commission": float(result.commission),
                    "commission_type": commission_type,
                    "final_price": float(result.final_price_usd),
                    "description": description,
                    "updated": datetime.now(UTC).isoformat(),
                }

                updated_examples.append(example)
                print(f"  ✅ ${item_price} + ${us_shipping} = ${result.commission} commission")

            except Exception as e:
                print(f"  ❌ Commission calculation failed for {description}: {e}")

        test_data = self.load_test_data()
        test_data["commission_examples"] = updated_examples
        self.save_test_data(test_data)

        print(f"📊 Updated {len(updated_examples)} commission examples")

    async def update_all(self) -> None:
        """Update all test data."""
        print("🔄 Starting comprehensive test data update...")

        await self.update_shipping_expectations()
        await self.update_currency_ranges()
        await self.update_commission_examples()
        await self.verify_test_urls()

        print("✅ Test data update complete!")

    def generate_pytest_fixtures(self) -> None:
        """Generate pytest fixture file from current test data."""
        print("📝 Generating pytest fixtures...")

        test_data = self.load_test_data()

        fixture_content = '''"""Auto-generated pytest fixtures from real data.

DO NOT EDIT MANUALLY - generated by data_updater.py
"""

import pytest
from decimal import Decimal
from datetime import datetime, UTC

# Auto-generated fixtures
'''

        # Generate shipping fixtures
        if "shipping_expectations" in test_data:
            fixture_content += '''
@pytest.fixture
def shipping_test_expectations():
    """Expected shipping costs for test items."""
    return {
'''
            for item, data in test_data["shipping_expectations"].items():
                fixture_content += f'        "{item}": {data},\n'
            fixture_content += "    }\n"

        # Generate commission fixtures
        if "commission_examples" in test_data:
            fixture_content += '''
@pytest.fixture
def commission_test_expectations():
    """Expected commission calculations."""
    return [
'''
            for example in test_data["commission_examples"]:
                fixture_content += f"        {example},\n"
            fixture_content += "    ]\n"

        # Write to file
        fixtures_file = self.fixtures_path / "generated_fixtures.py"
        with open(fixtures_file, "w") as f:
            f.write(fixture_content)

        print(f"📄 Generated fixtures: {fixtures_file}")


async def main():
    """Main updater function."""
    updater = TestDataUpdater()

    print("🚀 Test Data Updater")
    print("===================")

    await updater.update_all()
    updater.generate_pytest_fixtures()

    print("\n🎉 All updates completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
