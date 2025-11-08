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
_APP_LINK_SUFFIX = ".app.link"


def normalize_grailed_url(url: str) -> str:
    """Return canonical Grailed URL for listings shared via grailed.app.link.

    Args:
        url: Original URL that might be a Grailed shortlink.

    Returns:
        Canonical Grailed listing URL when shortlink payload contains it,
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

    # Only handle Appsflyer shortlinks explicitly.
    if not domain.endswith(_APP_LINK_SUFFIX):
        return url

    resolved = _resolve_app_link(parsed)
    if resolved:
        logger.debug("Resolved Grailed shortlink %s → %s", url, resolved)
        return resolved

    logger.debug("Failed to resolve Grailed shortlink %s", url)
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


__all__ = ["normalize_grailed_url"]
