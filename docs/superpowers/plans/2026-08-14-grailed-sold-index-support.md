# Grailed Sold Index Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Grailed Algolia client to query both active (`Listing_production`) and sold (`Listing_sold_production`) indexes in a single parallel multi-query, correctly identifying sold listings, calculating reference pricing, and displaying an explicit sold notice advisory.

**Architecture:** Single-roundtrip Algolia multi-query in `GrailedAlgoliaClient.get_listing_by_id`, setting `ItemData(is_sold=True, is_buyable=False)` when an item is only found in `Listing_sold_production`. The `SellerAdvisory` engine prioritizes `is_sold=True` and emits `ITEM_SOLD_MESSAGE`.

**Tech Stack:** Python 3.11+, Pydantic Settings, aiohttp, Algolia Search API, pytest-asyncio.

## Global Constraints
- `GRAILED_ALGOLIA_SOLD_INDEX_NAME` defaults to `"Listing_sold_production"`.
- Requests must be executed in a single POST to `https://{app_id}-dsn.algolia.net/1/indexes/*/queries` with both index queries inside `{"requests": [...]}`.
- Sold items must have `is_sold: True` and `is_buyable: False`.
- Sold advisory reason must be `"item_sold"`.
- All tests in `tests_new/` must pass with 0 failures and 0 skips.

---

### Task 1: Конфигурация `sold_index_name` и модель `ItemData.is_sold`

**Files:**
- Modify: `app/models.py:14-30`
- Modify: `app/config.py:131-150`
- Modify: `.env.example:16-25`
- Test: `tests_new/unit/test_config.py`

**Interfaces:**
- Consumes: None
- Produces: `ItemData.is_sold: bool = False`, `Config.algolia.sold_index_name: str`

- [ ] **Step 1: Write the failing tests in `tests_new/unit/test_config.py`**

```python
def test_grailed_algolia_config_sold_index_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """GrailedAlgoliaConfig should default sold_index_name to Listing_sold_production."""
    monkeypatch.delenv("GRAILED_ALGOLIA_SOLD_INDEX_NAME", raising=False)
    cfg = GrailedAlgoliaConfig()
    assert cfg.sold_index_name == "Listing_sold_production"


def test_grailed_algolia_config_sold_index_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """GrailedAlgoliaConfig should allow overriding sold_index_name via env."""
    monkeypatch.setenv("GRAILED_ALGOLIA_SOLD_INDEX_NAME", "custom_sold_index")
    cfg = GrailedAlgoliaConfig()
    assert cfg.sold_index_name == "custom_sold_index"


def test_item_data_is_sold_default() -> None:
    """ItemData model should default is_sold to False."""
    item = ItemData(price=Decimal("100"))
    assert item.is_sold is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests_new/unit/test_config.py -k "sold" -v`
Expected: FAIL with attribute errors.

- [ ] **Step 3: Implement `is_sold` in `app/models.py` and `sold_index_name` in `app/config.py`**

In `app/models.py`:
```python
class ItemData(BaseModel):
    price: Decimal
    shipping_us: Decimal = Decimal("0")
    is_buyable: bool = True
    is_sold: bool = False
    title: str | None = None
    image_url: str | None = None
```

In `app/config.py`:
```python
class GrailedAlgoliaConfig(BaseSettings):
    app_id: str = Field(default="MNRWEFSS2Q", validation_alias="GRAILED_ALGOLIA_APP_ID")
    api_key: str = Field(default="c89dbaddf15fe70e1941a109bf7c2a3d", validation_alias="GRAILED_ALGOLIA_API_KEY")
    index_name: str = Field(default="Listing_production", validation_alias="GRAILED_ALGOLIA_INDEX_NAME")
    sold_index_name: str = Field(default="Listing_sold_production", validation_alias="GRAILED_ALGOLIA_SOLD_INDEX_NAME")
    timeout_sec: float = Field(default=5.0, validation_alias="GRAILED_ALGOLIA_TIMEOUT_SEC")
```

Update `.env.example`:
```ini
GRAILED_ALGOLIA_SOLD_INDEX_NAME=Listing_sold_production
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests_new/unit/test_config.py -v`
Expected: PASS (all tests passing)

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/config.py .env.example tests_new/unit/test_config.py
git commit -m "feat(config): add sold_index_name and ItemData.is_sold"
```

---

### Task 2: Реализация Multi-query в `GrailedAlgoliaClient`

**Files:**
- Modify: `app/services/grailed_algolia.py`
- Test: `tests_new/unit/test_grailed_algolia_client.py`

**Interfaces:**
- Consumes: `Config.algolia.sold_index_name`, `ItemData.is_sold`
- Produces: `get_listing_by_id` returning `ItemData(is_sold=True, is_buyable=False)` when found in `Listing_sold_production`.

- [ ] **Step 1: Write the failing tests in `tests_new/unit/test_grailed_algolia_client.py`**

```python
SAMPLE_SOLD_HIT = {
    "id": 94370655,
    "title": "TORNADO MART DISTRESSED FLARED JEANS",
    "price": 117,
    "buynow": True,
    "sold": True,
    "shipping": {
        "us": {"amount": 25, "enabled": True}
    },
    "user": {
        "id": 888,
        "username": "vintage_archive",
        "seller_score": {"rating_average": 4.95, "rating_count": 80},
        "trusted_seller": True,
    },
    "cover_photo": {
        "url": "https://media-assets.grailed.com/prd/listing/temp/sold_jeans.jpg"
    },
}


@pytest.mark.asyncio
async def test_get_listing_by_id_sold_index_fallback():
    """When listing is missing from active index but present in sold index, return sold ItemData."""
    client = GrailedAlgoliaClient()
    mock_resp_data = {
        "results": [
            {"hits": [], "nbHits": 0},  # Active index: 0 hits
            {"hits": [SAMPLE_SOLD_HIT], "nbHits": 1},  # Sold index: 1 hit
        ]
    }

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id(94370655, mock_session)

    assert item is not None
    assert item.title == "TORNADO MART DISTRESSED FLARED JEANS"
    assert item.price == Decimal("117")
    assert item.shipping_us == Decimal("25")
    assert item.is_buyable is False  # Sold items are never buyable
    assert item.is_sold is True  # Marked as sold
    assert item.image_url == "https://media-assets.grailed.com/prd/listing/temp/sold_jeans.jpg"

    assert seller is not None
    assert seller.num_reviews == 80
    assert seller.avg_rating == 4.95
    assert seller.trusted_badge is True


@pytest.mark.asyncio
async def test_get_listing_by_id_multi_query_payload_structure():
    """Verify that multi-query payload queries both active and sold indexes."""
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [], "nbHits": 0}, {"hits": [], "nbHits": 0}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    await client.get_listing_by_id(12345, mock_session)

    mock_session.post.assert_called_once()
    _, kwargs = mock_session.post.call_args
    reqs = kwargs["json"]["requests"]
    assert len(reqs) == 2
    assert reqs[0]["indexName"] == client.index_name
    assert reqs[0]["params"] == "filters=id%3D12345&hitsPerPage=1"
    assert reqs[1]["indexName"] == client.sold_index_name
    assert reqs[1]["params"] == "filters=id%3D12345&hitsPerPage=1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests_new/unit/test_grailed_algolia_client.py -k "sold" -v`
Expected: FAIL.

- [ ] **Step 3: Update `GrailedAlgoliaClient` in `app/services/grailed_algolia.py`**

In `app/services/grailed_algolia.py`:
- In `__init__`:
  ```python
  self.sold_index_name = config.algolia.sold_index_name
  ```
- In `get_listing_by_id`:
  ```python
  payload = {
      "requests": [
          {
              "indexName": self.index_name,
              "params": f"filters=id%3D{listing_id}&hitsPerPage=1",
          },
          {
              "indexName": self.sold_index_name,
              "params": f"filters=id%3D{listing_id}&hitsPerPage=1",
          },
      ]
  }
  ```
- Parse multi-query results:
  ```python
  results = data.get("results", [])
  hit = None
  is_sold = False

  if results and results[0].get("hits"):
      hit = results[0]["hits"][0]
      is_sold = False
  elif len(results) > 1 and results[1].get("hits"):
      hit = results[1]["hits"][0]
      is_sold = True

  if not hit:
      logger.info(f"Listing ID {listing_id} not found in Algolia indexes (active/sold)")
      return None, None
  ```
- In item mapping:
  ```python
  is_buyable = False if is_sold else bool(hit.get("buynow", False))

  item_data = ItemData(
      price=price,
      shipping_us=shipping_us,
      is_buyable=is_buyable,
      is_sold=is_sold,
      title=title,
      image_url=image_url,
  )
  ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests_new/unit/test_grailed_algolia_client.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add app/services/grailed_algolia.py tests_new/unit/test_grailed_algolia_client.py
git commit -m "feat(services): add multi-index sold listing querying to GrailedAlgoliaClient"
```

---

### Task 3: Интеграция `ITEM_SOLD_MESSAGE` в `SellerAdvisory` и `ResponseFormatter`

**Files:**
- Modify: `app/bot/messages.py`
- Modify: `app/services/seller_advisory.py`
- Test: `tests_new/unit/test_seller_assessment.py`
- Test: `tests_new/unit/test_response_formatter.py`

**Interfaces:**
- Consumes: `ItemData.is_sold`
- Produces: `evaluate_seller_advisory` returning `reason="item_sold"` and `message=ITEM_SOLD_MESSAGE` when `item_data.is_sold is True`.

- [ ] **Step 1: Write failing tests in `tests_new/unit/test_seller_assessment.py` and `tests_new/unit/test_response_formatter.py`**

In `tests_new/unit/test_seller_assessment.py`:
```python
def test_sold_item_triggers_item_sold_advisory():
    """Sold items should trigger item_sold advisory reason and message."""
    item = ItemData(price=Decimal("100"), is_buyable=False, is_sold=True)
    seller = SellerData(num_reviews=50, avg_rating=5.0, trusted_badge=True)

    advisory = evaluate_seller_advisory(seller_data=seller, item_data=item)

    assert advisory.reason == "item_sold"
    assert "уже продан" in advisory.message
```

In `tests_new/unit/test_response_formatter.py`:
```python
@pytest.mark.asyncio
async def test_sold_listing_includes_sold_warning_and_breakdown():
    """Sold listing response should include breakdown and sold notice."""
    formatter = ResponseFormatter()
    item_data = ItemData(
        price=Decimal("117.00"),
        shipping_us=Decimal("25.00"),
        is_buyable=False,
        is_sold=True,
        title="Tornado Mart Flared Jeans",
    )
    seller_data = SellerData(
        num_reviews=80,
        avg_rating=4.95,
        trusted_badge=True,
    )
    scrape_result = {
        "success": True,
        "platform": "grailed",
        "item_data": item_data,
        "seller_data": seller_data,
        "error": None,
        "processing_time_ms": 120,
        "url": "https://www.grailed.com/listings/94370655-tornado-mart",
    }

    response = await formatter.format_item_response(scrape_result)

    assert "Tornado Mart Flared Jeans" in response
    assert "уже продан на Grailed" in response
    assert "$117" in response
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests_new/unit/test_seller_assessment.py tests_new/unit/test_response_formatter.py -k "sold" -v`
Expected: FAIL.

- [ ] **Step 3: Implement message and advisory logic**

In `app/bot/messages.py`:
```python
ITEM_SOLD_MESSAGE = (
    "⚠️ Этот товар уже продан на Grailed (архивное объявление).\n"
    "Выкуп невозможен, расчет стоимости приведен для справки."
)
```

In `app/services/seller_advisory.py`:
```python
from ..bot.messages import (
    ITEM_SOLD_MESSAGE,
    SELLER_LOW_RATING_MESSAGE,
    SELLER_NO_BUY_NOW_MESSAGE,
    SELLER_NO_REVIEWS_MESSAGE,
    SELLER_TECHNICAL_ISSUE_MESSAGE,
)


def evaluate_seller_advisory(
    seller_data: SellerData | None,
    item_data: ItemData | None = None,
) -> SellerAdvisory:
    """Evaluate seller reliability and listing buyability."""
    # Priority 1: Sold listing
    if item_data and item_data.is_sold:
        return SellerAdvisory(
            reason="item_sold",
            message=ITEM_SOLD_MESSAGE,
        )

    # Priority 2: Missing buy now price (offer-only)
    if item_data and not item_data.is_buyable:
        return SellerAdvisory(
            reason="no_buy_now_price",
            message=SELLER_NO_BUY_NOW_MESSAGE,
        )
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests_new/unit/test_seller_assessment.py tests_new/unit/test_response_formatter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/bot/messages.py app/services/seller_advisory.py tests_new/unit/test_seller_assessment.py tests_new/unit/test_response_formatter.py
git commit -m "feat(advisory): add item_sold advisory evaluation and message"
```

---

### Task 4: Интеграционное тестирование и обновление диагностического инструмента

**Files:**
- Modify: `tests_new/integration/test_grailed_orchestration.py`
- Modify: `scripts/probe_grailed_algolia.py`
- Test: `tests_new/`

**Interfaces:**
- Consumes: `GrailedAlgoliaClient`, `ScrapingOrchestrator`, `SellerAdvisory`
- Produces: 100% passing test suite across all units and integration tests, updated probe utility with `--sold` support.

- [ ] **Step 1: Write integration tests in `tests_new/integration/test_grailed_orchestration.py`**

```python
@pytest.mark.asyncio
async def test_orchestrator_grailed_sold_listing_flow() -> None:
    """Test full orchestrator flow for sold listing on Grailed."""
    mock_sold_item = ItemData(
        price=Decimal("117.00"),
        shipping_us=Decimal("25.00"),
        is_buyable=False,
        is_sold=True,
        title="Tornado Mart Flared Jeans",
        image_url="https://example.com/sold.jpg",
    )
    mock_seller = SellerData(
        num_reviews=80,
        avg_rating=4.95,
        trusted_badge=True,
    )

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
        new_callable=AsyncMock,
        return_value=(mock_sold_item, mock_seller),
    ) as mock_algolia:
        async with aiohttp.ClientSession() as session:
            url = "https://www.grailed.com/listings/94370655-tornado-mart"
            result = await scraping_orchestrator.scrape_item_listing(url, session)

            mock_algolia.assert_called_once_with("94370655", session)
            assert result["success"] is True
            assert result["platform"] == "grailed"
            assert result["item_data"].is_sold is True
            assert result["item_data"].is_buyable is False

            # Format response and verify advisory
            response = await response_formatter.format_item_response(result)
            assert "уже продан на Grailed" in response
            assert "$117" in response
```

- [ ] **Step 2: Update `scripts/probe_grailed_algolia.py` to support `--sold` and multi-query probing**

Update `scripts/probe_grailed_algolia.py` to query both `Listing_production` and `Listing_sold_production` in `--ids`, displaying `[SOLD]` badge for sold items.

- [ ] **Step 3: Run full test suite and live probe**

Run:
1. `pytest tests_new/ -v`
2. `python scripts/probe_grailed_algolia.py --ids 99406229,94370655,85070048 -v`

Expected:
1. All unit & integration tests pass (0 failures, 0 skips).
2. Probe shows `[OK] 99406229 [ACTIVE]`, `[OK] 94370655 [SOLD]`, and `[FAIL] 85070048 [NOT FOUND]`.

- [ ] **Step 4: Commit**

```bash
git add tests_new/integration/test_grailed_orchestration.py scripts/probe_grailed_algolia.py
git commit -m "test(integration): add sold listing orchestration tests and probe support"
```
