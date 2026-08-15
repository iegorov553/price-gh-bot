#!/usr/bin/env python3
"""Diagnostic read-only probe for Grailed Algolia search index.

Isolated testing tool for verifying Algolia availability, schema, latency,
and data mapping. Does NOT modify or import production code.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import aiohttp

DEFAULT_APP_ID = os.getenv("GRAILED_ALGOLIA_APP_ID", "MNRWEFSS2Q")
DEFAULT_API_KEY = os.getenv("GRAILED_ALGOLIA_API_KEY", "c89dbaddf15fe70e1941a109bf7c2a3d")
DEFAULT_INDEX_NAME = os.getenv("GRAILED_ALGOLIA_INDEX_NAME", "Listing_production")
DEFAULT_SOLD_INDEX_NAME = os.getenv("GRAILED_ALGOLIA_SOLD_INDEX_NAME", "Listing_sold_production")

INCIDENT_IDS = ["99406229", "101466749", "91286492", "102514433"]


@dataclass
class MappedItem:
    """Mapped representation matching ItemData."""

    listing_id: int
    title: str | None
    price_usd: Decimal | None
    shipping_us: Decimal | None
    is_buyable: bool
    make_offer: bool
    sold: bool
    deleted: bool
    image_url: str | None


@dataclass
class MappedSeller:
    """Mapped representation matching SellerData."""

    username: str | None
    num_reviews: int
    avg_rating: float
    trusted_badge: bool
    technical_issue: bool


@dataclass
class ProbeResult:
    """Result of probing a single listing ID."""

    listing_id: str
    success: bool
    http_status: int
    latency_ms: float
    exact_match: bool
    item: MappedItem | None = None
    seller: MappedSeller | None = None
    raw_hit_keys: list[str] | None = None
    error: str | None = None
    is_sold: bool = False
    index_found: str | None = None


def extract_listing_id(target: str) -> str:
    """Extract numeric listing ID from URL, path, or raw ID string."""
    target = target.strip()
    if target.isdigit():
        return target

    # Handle URLs like https://www.grailed.com/listings/99406229-vissla-board-shorts
    match = re.search(r"/listings/(\d+)", target)
    if match:
        return match.group(1)

    # Handle numeric patterns anywhere in string
    match = re.search(r"\b(\d{7,10})\b", target)
    if match:
        return match.group(1)

    return target


def map_algolia_hit(hit: dict[str, Any], is_sold: bool = False) -> tuple[MappedItem, MappedSeller]:
    """Map raw Algolia hit to MappedItem and MappedSeller models."""
    listing_id = int(hit.get("id") or hit.get("objectID") or 0)
    title = hit.get("title")

    raw_price = hit.get("price")
    price_usd = Decimal(str(raw_price)) if raw_price is not None else None

    # Parse US shipping
    shipping_data = hit.get("shipping") or {}
    shipping_us: Decimal | None = None
    if isinstance(shipping_data, dict):
        us_ship = shipping_data.get("us") or {}
        if isinstance(us_ship, dict):
            enabled = us_ship.get("enabled", False)
            amt = us_ship.get("amount")
            if enabled and amt is not None:
                shipping_us = Decimal(str(amt))
            elif not enabled:
                shipping_us = Decimal("0")
            elif amt is not None:
                shipping_us = Decimal(str(amt))

    is_buyable = False if is_sold else bool(hit.get("buynow", False))
    make_offer = bool(hit.get("makeoffer", False))
    sold = is_sold or bool(hit.get("sold", False))
    deleted = bool(hit.get("deleted", False))

    cover_photo = hit.get("cover_photo") or {}
    image_url = cover_photo.get("image_url") or cover_photo.get("url")

    # Map seller data
    user_data = hit.get("user") or {}
    username = user_data.get("username")
    seller_score = user_data.get("seller_score") or {}
    num_reviews = int(seller_score.get("rating_count") or 0)
    avg_rating = float(seller_score.get("rating_average") or 0.0)
    trusted_badge = bool(user_data.get("trusted_seller", False))

    item = MappedItem(
        listing_id=listing_id,
        title=title,
        price_usd=price_usd,
        shipping_us=shipping_us,
        is_buyable=is_buyable,
        make_offer=make_offer,
        sold=sold,
        deleted=deleted,
        image_url=image_url,
    )

    seller = MappedSeller(
        username=username,
        num_reviews=num_reviews,
        avg_rating=round(avg_rating, 2),
        trusted_badge=trusted_badge,
        technical_issue=False,
    )

    return item, seller


async def query_algolia_single(
    session: aiohttp.ClientSession,
    listing_id: str,
    app_id: str = DEFAULT_APP_ID,
    api_key: str = DEFAULT_API_KEY,
    index_name: str = DEFAULT_INDEX_NAME,
    sold_index_name: str = DEFAULT_SOLD_INDEX_NAME,
    timeout_sec: float = 5.0,
) -> ProbeResult:
    """Execute a multi-query for a listing ID against active and sold Algolia indexes."""
    url = f"https://{app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"
    headers = {
        "x-algolia-application-id": app_id,
        "x-algolia-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "requests": [
            {
                "indexName": index_name,
                "params": f"filters=id%3D{listing_id}&hitsPerPage=1",
            },
            {
                "indexName": sold_index_name,
                "params": f"filters=id%3D{listing_id}&hitsPerPage=1",
            },
        ]
    }

    start_t = time.perf_counter()
    try:
        async with session.post(
            url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout_sec),
        ) as resp:
            latency_ms = (time.perf_counter() - start_t) * 1000
            status = resp.status

            if status != 200:
                err_text = await resp.text()
                return ProbeResult(
                    listing_id=listing_id,
                    success=False,
                    http_status=status,
                    latency_ms=round(latency_ms, 2),
                    exact_match=False,
                    error=f"HTTP {status}: {err_text[:200]}",
                )

            data = await resp.json()
            results = data.get("results", [])
            if not results:
                return ProbeResult(
                    listing_id=listing_id,
                    success=False,
                    http_status=200,
                    latency_ms=round(latency_ms, 2),
                    exact_match=False,
                    error="Empty results list",
                )

            hit = None
            is_sold = False
            index_found = None

            if results and results[0].get("hits"):
                hit = results[0]["hits"][0]
                is_sold = False
                index_found = index_name
            elif len(results) > 1 and results[1].get("hits"):
                hit = results[1]["hits"][0]
                is_sold = True
                index_found = sold_index_name

            if not hit:
                return ProbeResult(
                    listing_id=listing_id,
                    success=False,
                    http_status=200,
                    latency_ms=round(latency_ms, 2),
                    exact_match=False,
                    error="0 hits found",
                )

            hit_id = str(hit.get("id") or hit.get("objectID") or "")
            exact_match = hit_id == listing_id

            item, seller = map_algolia_hit(hit, is_sold=is_sold)
            return ProbeResult(
                listing_id=listing_id,
                success=True,
                http_status=200,
                latency_ms=round(latency_ms, 2),
                exact_match=exact_match,
                item=item,
                seller=seller,
                raw_hit_keys=list(hit.keys()),
                is_sold=is_sold,
                index_found=index_found,
            )

    except asyncio.TimeoutError:
        latency_ms = (time.perf_counter() - start_t) * 1000
        return ProbeResult(
            listing_id=listing_id,
            success=False,
            http_status=0,
            latency_ms=round(latency_ms, 2),
            exact_match=False,
            error=f"Timeout after {timeout_sec}s",
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start_t) * 1000
        return ProbeResult(
            listing_id=listing_id,
            success=False,
            http_status=0,
            latency_ms=round(latency_ms, 2),
            exact_match=False,
            error=str(e),
        )


async def run_probe(
    ids: list[str],
    app_id: str = DEFAULT_APP_ID,
    api_key: str = DEFAULT_API_KEY,
    index_name: str = DEFAULT_INDEX_NAME,
    sold_index_name: str = DEFAULT_SOLD_INDEX_NAME,
    verbose: bool = False,
) -> list[ProbeResult]:
    """Run probe sequentially for a list of listing IDs."""
    results: list[ProbeResult] = []
    async with aiohttp.ClientSession() as session:
        for lid in ids:
            cleaned_id = extract_listing_id(lid)
            res = await query_algolia_single(
                session=session,
                listing_id=cleaned_id,
                app_id=app_id,
                api_key=api_key,
                index_name=index_name,
                sold_index_name=sold_index_name,
            )
            results.append(res)
            if verbose:
                if res.success and res.exact_match:
                    status_badge = "[SOLD]" if res.is_sold else "[ACTIVE]"
                    result_tag = "[OK]"
                else:
                    status_badge = "[NOT FOUND]" if res.error == "0 hits found" else "[ERROR]"
                    result_tag = "[FAIL]"

                print(f"{result_tag} ID: {res.listing_id} {status_badge} | Status: {res.http_status} | "
                      f"Latency: {res.latency_ms}ms | Exact: {res.exact_match}")
                if res.item:
                    print(f"   Title: {res.item.title}")
                    print(f"   Price: ${res.item.price_usd} | US Ship: ${res.item.shipping_us} | BuyNow: {res.item.is_buyable}")
                if res.seller:
                    print(f"   Seller: @{res.seller.username} | Rating: {res.seller.avg_rating} | Reviews: {res.seller.num_reviews} | Trusted: {res.seller.trusted_badge}")
                if res.error:
                    print(f"   Error: {res.error}")
                print("-" * 50)
    return results


async def run_soak_test(
    ids: list[str],
    iterations: int = 20,
    interval_sec: float = 1.0,
    app_id: str = DEFAULT_APP_ID,
    api_key: str = DEFAULT_API_KEY,
    index_name: str = DEFAULT_INDEX_NAME,
    sold_index_name: str = DEFAULT_SOLD_INDEX_NAME,
) -> dict[str, Any]:
    """Run a soak test repeating queries across listing IDs."""
    print(f"=== Starting Soak Test: {iterations} iterations, interval {interval_sec}s ===")
    results: list[ProbeResult] = []
    latencies: list[float] = []

    async with aiohttp.ClientSession() as session:
        for i in range(iterations):
            lid = ids[i % len(ids)]
            cleaned_id = extract_listing_id(lid)
            res = await query_algolia_single(
                session=session,
                listing_id=cleaned_id,
                app_id=app_id,
                api_key=api_key,
                index_name=index_name,
                sold_index_name=sold_index_name,
            )
            results.append(res)
            latencies.append(res.latency_ms)
            status_str = f"HTTP {res.http_status}" if res.http_status else "ERR"
            badge = f" [{'SOLD' if res.is_sold else 'ACTIVE'}]" if res.exact_match else ""
            print(f"[{i+1:02d}/{iterations:02d}] ID: {cleaned_id}{badge} | {status_str} | {res.latency_ms:.1f}ms | Match: {res.exact_match}")
            if i < iterations - 1:
                await asyncio.sleep(interval_sec)

    latencies.sort()
    success_count = sum(1 for r in results if r.success and r.exact_match)
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
    min_lat = min(latencies) if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0

    summary = {
        "total_requests": iterations,
        "successful_exact_matches": success_count,
        "success_rate_pct": round((success_count / iterations) * 100, 2),
        "latency_min_ms": round(min_lat, 2),
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "latency_max_ms": round(max_lat, 2),
    }

    print("\n=== Soak Test Summary ===")
    for k, v in summary.items():
        print(f"{k}: {v}")
    return summary


async def run_fault_tolerance_tests(
    valid_id: str = "99406229",
) -> list[dict[str, Any]]:
    """Simulate faulty configurations to verify error handling."""
    print("=== Starting Fault Tolerance Tests ===")
    test_cases = [
        ("Invalid API Key", DEFAULT_APP_ID, "invalid_key_12345", DEFAULT_INDEX_NAME, DEFAULT_SOLD_INDEX_NAME, valid_id, 403),
        ("Invalid App ID", "INVALID_APP", DEFAULT_API_KEY, DEFAULT_INDEX_NAME, DEFAULT_SOLD_INDEX_NAME, valid_id, 400),
        ("Invalid Index Name", DEFAULT_APP_ID, DEFAULT_API_KEY, "NonExistent_index", "NonExistent_sold_index", valid_id, 400),
        ("Non-existent Listing ID", DEFAULT_APP_ID, DEFAULT_API_KEY, DEFAULT_INDEX_NAME, DEFAULT_SOLD_INDEX_NAME, "999999999999", 200),
    ]

    fault_results = []
    async with aiohttp.ClientSession() as session:
        for name, app_id, api_key, index_name, sold_index_name, lid, expected_status in test_cases:
            res = await query_algolia_single(
                session=session,
                listing_id=lid,
                app_id=app_id,
                api_key=api_key,
                index_name=index_name,
                sold_index_name=sold_index_name,
            )
            passed = (res.http_status == expected_status) or (expected_status == 400 and res.http_status in [0, 400, 403, 404])
            if expected_status == 200 and lid == "999999999999":
                passed = (res.http_status == 200 and not res.exact_match and res.error == "0 hits found")

            print(f"[{'PASS' if passed else 'FAIL'}] {name} -> Status: {res.http_status} (Expected: ~{expected_status}), Exact: {res.exact_match}, Error: {res.error}")
            fault_results.append({
                "test_name": name,
                "passed": passed,
                "http_status": res.http_status,
                "exact_match": res.exact_match,
                "error": res.error,
            })
    return fault_results


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Diagnostic Grailed Algolia probe")
    parser.add_argument("--ids", type=str, help="Comma-separated listing IDs or URLs")
    parser.add_argument("--incidents", action="store_true", help="Run 4 incident listings")
    parser.add_argument("--soak", action="store_true", help="Run soak test")
    parser.add_argument("--iterations", type=int, default=20, help="Number of soak test iterations")
    parser.add_argument("--interval", type=float, default=1.0, help="Interval between soak test requests")
    parser.add_argument("--test-faults", action="store_true", help="Run fault tolerance simulation")
    parser.add_argument("--json", action="store_true", help="Output sanitized JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--index", type=str, default=DEFAULT_INDEX_NAME, help="Algolia active index name")
    parser.add_argument("--sold-index", type=str, default=DEFAULT_SOLD_INDEX_NAME, help="Algolia sold index name")

    args = parser.parse_args()

    ids_to_test = []
    if args.ids:
        ids_to_test = [x.strip() for x in args.ids.split(",") if x.strip()]
    elif args.incidents or not (args.soak or args.test_faults):
        ids_to_test = INCIDENT_IDS

    if args.test_faults:
        asyncio.run(run_fault_tolerance_tests())
        return

    if args.soak:
        soak_ids = ids_to_test if ids_to_test else INCIDENT_IDS
        summary = asyncio.run(
            run_soak_test(
                ids=soak_ids,
                iterations=args.iterations,
                interval_sec=args.interval,
                index_name=args.index,
                sold_index_name=args.sold_index,
            )
        )
        if args.json:
            print(json.dumps(summary, indent=2))
        return

    results = asyncio.run(
        run_probe(
            ids_to_test,
            index_name=args.index,
            sold_index_name=args.sold_index,
            verbose=args.verbose or not args.json,
        )
    )

    if args.json:
        serializable = []
        for r in results:
            d = asdict(r)
            if d.get("item") and d["item"].get("price_usd"):
                d["item"]["price_usd"] = str(d["item"]["price_usd"])
            if d.get("item") and d["item"].get("shipping_us"):
                d["item"]["shipping_us"] = str(d["item"]["shipping_us"])
            serializable.append(d)
        print(json.dumps(serializable, indent=2))


if __name__ == "__main__":
    main()

