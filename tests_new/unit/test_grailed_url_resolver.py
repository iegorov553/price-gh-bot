"""Unit tests for Grailed URL normalization utilities."""

from __future__ import annotations

import base64
import json

import pytest

from app.scrapers.grailed_url_resolver import normalize_grailed_url


def _build_shortlink(payload: dict[str, str]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    # Appsflyer strips trailing padding characters.
    encoded = encoded.rstrip("=")
    return f"https://grailed.app.link/share?data={encoded}"


def test_normalize_grailed_url_from_real_payload() -> None:
    url = (
        "https://grailed.app.link?channel=Pasteboard&feature=mobile-share&type=0&duration=0"
        "&source=ios&data=eyIkY3JlYXRpb25fdGltZXN0YW1wIjoxNzYyMjcwOTE5Nzc3LCIkb2dfZGVzY3Jp"
        "cHRpb24iOiJDYXJvbCBDaHJpc3RpYW4gUG9lbGwgQ3JlYW0gU2lkZS1aaXAgQm9vdHMiLCIkb2dfaW1hZ2"
        "VfdXJsIjoiaHR0cHM6Ly9tZWRpYS1hc3NldHMuZ3JhaWxlZC5jb20vcHJkL2xpc3RpbmcvdGVtcC84ZjQ0"
        "MGQ2MmQwYzQ0MDZhYmNiNjAzODE4MGU2MmRiNSIsIiRjYW5vbmljYWxfdXJsIjoiaHR0cHM6Ly93d3cuZ3J"
        "haWxlZC5jb20vbGlzdGluZ3MvODYzMDk5OTgiLCIkb2dfdGl0bGUiOiJDYXJvbCBDaHJpc3RpYW4gUG9lbG"
        "wgQ3JlYW0gU2lkZS1aaXAgQm9vdHMiLCIkZmFsbGJhY2tfdXJsIjoiaHR0cHM6Ly93d3cuZ3JhaWxlZC5jb"
        "20vbGlzdGluZ3MvODYzMDk5OTgiLCIkY2Fub25pY2FsX2lkZW50aWZpZXIiOiIvbGlzdGluZ3MvODYzMDk5"
        "OTgifQ%3D%3D"
    )

    expected = "https://www.grailed.com/listings/86309998"
    assert normalize_grailed_url(url) == expected


def test_normalize_grailed_url_uses_canonical_identifier() -> None:
    payload = {"$canonical_identifier": "/listings/123456-test-item"}
    url = _build_shortlink(payload)

    expected = "https://www.grailed.com/listings/123456-test-item"
    assert normalize_grailed_url(url) == expected


def test_normalize_grailed_url_returns_original_on_decode_error() -> None:
    url = "https://grailed.app.link/share?data=@@@invalid@@@"
    assert normalize_grailed_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.grailed.com/listings/999",
        "https://grailed.com/listings/1000",
    ],
)
def test_normalize_grailed_url_passthrough_for_canonical_links(url: str) -> None:
    assert normalize_grailed_url(url) == url


def test_normalize_grailed_url_from_onelink_query_param() -> None:
    url = "https://grailed.onelink.me/1LT8/abc?deep_link_value=%2Flistings%2F103877007"
    assert normalize_grailed_url(url) == "https://www.grailed.com/listings/103877007"


@pytest.mark.asyncio
async def test_async_normalize_grailed_onelink_redirect_listing() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.scrapers.grailed_url_resolver import async_normalize_grailed_url

    shortlink = "https://grailed.onelink.me/1LT8/7o7iovrk"
    target = "https://www.grailed.com/listings/103877007?c=listing"

    mock_resp = MagicMock()
    mock_resp.status = 301
    mock_resp.headers = {"Location": target}

    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_resp
    mock_context.__aexit__.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_context

    resolved = await async_normalize_grailed_url(shortlink, mock_session)
    assert resolved == target
    mock_session.get.assert_called_once_with(shortlink, allow_redirects=False)


@pytest.mark.asyncio
async def test_async_normalize_grailed_onelink_redirect_seller_profile() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.scrapers.grailed_url_resolver import async_normalize_grailed_url

    shortlink = "https://grailed.onelink.me/1LT8/seller123"
    target = "https://www.grailed.com/users/12345-grailedseller"

    mock_resp = MagicMock()
    mock_resp.status = 301
    mock_resp.headers = {"Location": target}

    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_resp
    mock_context.__aexit__.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_context

    resolved = await async_normalize_grailed_url(shortlink, mock_session)
    assert resolved == target
