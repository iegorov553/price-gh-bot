"""Utilities for resolving and normalizing Grailed URLs.

Handles Grailed shortlinks served via grailed.app.link (Appsflyer) by decoding
their payload and extracting canonical marketplace URLs. Ensures that all
scraping operations operate on full https://www.grailed.com/ URLs.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.parse import ParseResult, parse_qs, urljoin, urlparse

logger = logging.getLogger(__name__)

_GRAILED_DOMAIN = "grailed.com"
_SHORTLINK_SUFFIXES = (".app.link", ".onelink.me")


def is_grailed_shortlink(url: str) -> bool:
    """Check if URL is a Grailed shortlink (Branch.io or AppsFlyer OneLink)."""
    try:
        domain = urlparse(url).netloc.lower()
        return any(domain.endswith(suffix) for suffix in _SHORTLINK_SUFFIXES)
    except Exception:
        return False


def normalize_grailed_url(url: str) -> str:
    """Return canonical Grailed URL for listings shared via shortlinks.

    Supports Branch.io (grailed.app.link) and AppsFlyer OneLink (grailed.onelink.me).

    Args:
        url: Original URL that might be a Grailed shortlink.

    Returns:
        Canonical Grailed listing URL when shortlink payload or query contains it,
        otherwise returns the original URL.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    domain = parsed.netloc.lower()

    # Already a grailed.com URL – nothing to do.
    if _GRAILED_DOMAIN in domain:
        return url

    # Only handle supported shortlinks explicitly.
    if not any(domain.endswith(suffix) for suffix in _SHORTLINK_SUFFIXES):
        return url

    # Try static query parameters (e.g. AppsFlyer deep_link_value or af_dp)
    query = parse_qs(parsed.query)
    for q_key in ("deep_link_value", "af_dp"):
        vals = query.get(q_key, [])
        if vals:
            candidate = vals[0]
            resolved = _ensure_grailed_url(candidate)
            if resolved:
                logger.debug("Resolved Grailed shortlink via query %s → %s", url, resolved)
                return resolved

    resolved = _resolve_app_link(parsed)
    if resolved:
        logger.debug("Resolved Grailed shortlink %s → %s", url, resolved)
        return resolved

    logger.debug("Failed to resolve Grailed shortlink %s", url)
    return url


async def async_normalize_grailed_url(url: str, session: Any = None) -> str:
    """Return canonical Grailed URL for listings shared via shortlinks.

    Attempts static payload decoding first. If static resolution fails,
    attempts HTTP GET/HEAD redirect resolution or headless browser resolution.
    """
    normalized = normalize_grailed_url(url)
    if _GRAILED_DOMAIN in urlparse(normalized).netloc.lower():
        return normalized

    parsed = urlparse(url)
    if not any(parsed.netloc.lower().endswith(suffix) for suffix in _SHORTLINK_SUFFIXES):
        return url

    # Try HTTP redirect resolution via session
    if session is not None:
        # Fast check: GET with allow_redirects=False to inspect 301/302 Location header.
        # AppsFlyer OneLink rejects HEAD with 405 Method Not Allowed, but returns 301 on GET.
        try:
            async with session.get(url, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location")
                    if location:
                        target = urljoin(url, location)
                        if _GRAILED_DOMAIN in urlparse(target).netloc.lower():
                            logger.debug(
                                "Resolved Grailed shortlink via GET 301 %s → %s", url, target
                            )
                            return target
        except Exception as exc:
            logger.debug("HTTP GET allow_redirects=False failed for %s: %s", url, exc)

        try:
            async with session.head(url, allow_redirects=True) as resp:
                final_url = str(resp.url)
                if _GRAILED_DOMAIN in urlparse(final_url).netloc.lower():
                    logger.debug("Resolved Grailed shortlink via HTTP HEAD %s → %s", url, final_url)
                    return final_url
        except Exception as exc:
            logger.debug("HTTP HEAD shortlink resolution failed for %s: %s", url, exc)

        try:
            async with session.get(url, allow_redirects=True) as resp:
                final_url = str(resp.url)
                if _GRAILED_DOMAIN in urlparse(final_url).netloc.lower():
                    logger.debug("Resolved Grailed shortlink via HTTP GET %s → %s", url, final_url)
                    return final_url
        except Exception as exc:
            logger.debug("HTTP GET shortlink resolution failed for %s: %s", url, exc)

    # Try headless browser redirect resolution
    try:
        from .headless import resolve_shortlink_headless

        headless_resolved = await resolve_shortlink_headless(url)
        if headless_resolved and _GRAILED_DOMAIN in urlparse(headless_resolved).netloc.lower():
            logger.debug("Resolved Grailed shortlink via Headless %s → %s", url, headless_resolved)
            return headless_resolved
    except Exception as exc:
        logger.debug("Headless shortlink resolution failed for %s: %s", url, exc)

    return url


def _resolve_app_link(parsed_url: ParseResult) -> str | None:
    """Decode grailed.app.link payload and extract canonical URL."""
    query = parse_qs(parsed_url.query)
    data_payload = query.get("data", [])

    if not data_payload:
        return None

    payload = _decode_payload(data_payload[0])
    if not payload:
        return None

    candidates = _extract_candidates(payload)
    for candidate in candidates:
        resolved = _ensure_grailed_url(candidate)
        if resolved:
            return resolved

    return None


def _decode_payload(encoded: str) -> dict[str, Any] | None:
    """Decode base64 urlsafe payload shipped with Appsflyer shortlinks."""
    try:
        padding = "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(encoded + padding)
        decoded = raw.decode("utf-8")
        data = json.loads(decoded)
        if isinstance(data, dict):
            return data
        logger.debug("Shortlink payload is not a dict: %s", type(data))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.debug("Failed to decode Grailed shortlink payload: %s", exc)
    return None


def _extract_candidates(payload: dict[str, Any]) -> list[str]:
    """Return potential URL candidates from decoded payload."""
    candidate_keys = [
        "$canonical_url",
        "$fallback_url",
        "$og_url",
        "$og_image_url",
        "$og_title",
        "$canonical_identifier",
    ]

    candidates: list[str] = []

    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    return candidates


def _ensure_grailed_url(value: str) -> str | None:
    """Validate candidate and build full Grailed URL when necessary."""
    value = value.strip()

    # Handle relative identifiers like "/listings/123".
    if value.startswith("/"):
        return urljoin("https://www.grailed.com", value)

    try:
        parsed = urlparse(value)
    except Exception:
        return None

    netloc = parsed.netloc.lower()
    if not netloc:
        return None

    if _GRAILED_DOMAIN not in netloc:
        return None

    if not parsed.scheme:
        return f"https://{parsed.netloc}{parsed.path or ''}"

    return value


__all__ = ["normalize_grailed_url", "async_normalize_grailed_url", "is_grailed_shortlink"]
