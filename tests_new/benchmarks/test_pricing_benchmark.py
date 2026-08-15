"""Performance benchmarks for core pricing and shipping calculations."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from app.scrapers.grailed_page import classify_grailed_html
from app.services.shipping import estimate_shopfans_shipping

try:
    import pytest_benchmark  # noqa: F401
except ImportError:

    @pytest.fixture
    def benchmark() -> Callable[..., Any]:
        """Fallback benchmark fixture when pytest-benchmark is not installed."""

        def _runner(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        return _runner


@pytest.mark.benchmark
def test_benchmark_shipping_estimation(benchmark: Any) -> None:
    """Benchmark Shopfans shipping estimation logic."""
    title = "Vintage Supreme Box Logo Heavyweight Hoodie Black Large"
    order_value = Decimal("250.00")

    result = benchmark(estimate_shopfans_shipping, title, order_value)
    assert result.cost_usd > Decimal("0")


@pytest.mark.benchmark
def test_benchmark_grailed_html_classification(benchmark: Any) -> None:
    """Benchmark Grailed HTML page classifier."""
    sample_html = '<html><head><title>Item</title></head><body><script id="__NEXT_DATA__">{}</script></body></html>'

    result = benchmark(classify_grailed_html, sample_html)
    assert result.value == "listing"
