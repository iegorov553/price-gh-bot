"""Tests for Grailed scraper buy-now detection using Next.js data."""

import json
from decimal import Decimal

from bs4 import BeautifulSoup

from app.scrapers.grailed_scraper import _extract_price_and_buyability


def _build_soup(listing_payload: dict) -> BeautifulSoup:
    wrapper = {"props": {"pageProps": {"listing": listing_payload}}}
    html = f"<html><script id='__NEXT_DATA__'>{json.dumps(wrapper)}</script></html>"
    return BeautifulSoup(html, "lxml")


def test_offer_only_listing_detected_as_non_buyable() -> None:
    """Listings without price and buy-now flags should be treated as offer-only."""
    soup = _build_soup({"price": None, "buyNow": False, "makeOffer": True, "status": "offer-only"})

    price, buyable = _extract_price_and_buyability("https://example.com", soup)

    assert price is None
    assert buyable is False


def test_listing_with_price_flags_offer_only_when_buy_now_false() -> None:
    """Price without buy-now flag should be treated as offer-only to trigger warning."""
    soup = _build_soup({"price": 285, "buyNow": False, "makeOffer": True})

    price, buyable = _extract_price_and_buyability("https://example.com", soup)

    assert price == Decimal("285")
    assert buyable is False


def test_explicit_buy_now_listing_detected_as_buyable() -> None:
    """Grailed listing with buy-now flag must stay buyable."""
    soup = _build_soup({"price": "$150", "buyNow": True, "makeOffer": True})

    price, buyable = _extract_price_and_buyability("https://example.com", soup)

    assert price == Decimal("150")
    assert buyable is True
