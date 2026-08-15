"""Grailed Algolia search index client.

Extracts structured listing and seller profile data directly from Grailed's
Algolia backend, bypassing HTML scraping and browser-based anti-bot hurdles.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import aiohttp

from ..config import config
from ..models import ItemData, SellerData

logger = logging.getLogger(__name__)


class GrailedAlgoliaClient:
    """Client for querying Grailed listings and seller profiles via Algolia."""

    def __init__(self) -> None:
        self.cfg = config.algolia
        self.index_name = self.cfg.index_name
        self.sold_index_name = self.cfg.sold_index_name

    def _get_headers(self) -> dict[str, str]:
        return {
            "x-algolia-application-id": self.cfg.app_id,
            "x-algolia-api-key": self.cfg.api_key,
            "Content-Type": "application/json",
        }

    def _get_endpoint_url(self) -> str:
        return f"https://{self.cfg.app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"

    def _map_hit_to_models(
        self, hit: dict[str, Any], is_sold: bool = False
    ) -> tuple[ItemData | None, SellerData | None]:
        """Convert a raw Algolia hit into ItemData and SellerData."""
        try:
            title = hit.get("title")
            raw_price = hit.get("price")
            if raw_price is None:
                logger.warning("Algolia hit missing price for id: %s", hit.get("id"))
                return None, None

            price = Decimal(str(raw_price))

            # US shipping mapping
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

            is_buyable = False if is_sold else bool(hit.get("buynow", False))

            # Cover image URL
            cover_photo = hit.get("cover_photo") or {}
            image_url: str | None = None
            if isinstance(cover_photo, dict):
                image_url = cover_photo.get("image_url") or cover_photo.get("url")

            item_data = ItemData(
                price=price,
                shipping_us=shipping_us,
                is_buyable=is_buyable,
                title=str(title).strip() if title else None,
                image_url=image_url,
                is_sold=is_sold,
            )

            # Seller mapping
            user_data = hit.get("user") or {}
            seller_score = user_data.get("seller_score") or {}
            num_reviews = int(seller_score.get("rating_count") or 0)
            avg_rating = round(float(seller_score.get("rating_average") or 0.0), 2)
            trusted_badge = bool(user_data.get("trusted_seller", False))

            seller_data = SellerData(
                num_reviews=num_reviews,
                avg_rating=avg_rating,
                trusted_badge=trusted_badge,
                technical_issue=False,
            )

            return item_data, seller_data

        except Exception as exc:
            logger.error("Failed to map Algolia hit to models: %s", exc, exc_info=True)
            return None, None

    async def get_listing_by_id(
        self, listing_id: int | str, session: aiohttp.ClientSession
    ) -> tuple[ItemData | None, SellerData | None]:
        """Fetch listing item data and seller data by listing ID."""
        cleaned_id = str(listing_id).strip()
        payload = {
            "requests": [
                {
                    "indexName": self.index_name,
                    "params": f"filters=id%3D{cleaned_id}&hitsPerPage=1",
                },
                {
                    "indexName": self.sold_index_name,
                    "params": f"filters=id%3D{cleaned_id}&hitsPerPage=1",
                },
            ]
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.cfg.timeout_sec)
            async with session.post(
                self._get_endpoint_url(),
                headers=self._get_headers(),
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    if results:
                        if results[0].get("hits"):
                            hit = results[0]["hits"][0]
                            return self._map_hit_to_models(hit, is_sold=False)
                        elif len(results) > 1 and results[1].get("hits"):
                            hit = results[1]["hits"][0]
                            return self._map_hit_to_models(hit, is_sold=True)
                    logger.info("Listing ID %s not found in Algolia indexes", cleaned_id)
                    return None, None
                else:
                    err_body = await resp.text()
                    logger.error(
                        "Algolia query failed with HTTP %s for listing %s: %s",
                        resp.status,
                        cleaned_id,
                        err_body[:200],
                    )
                    return None, None

        except TimeoutError:
            logger.warning("Algolia query timed out for listing %s", cleaned_id)
            return None, None
        except Exception as exc:
            logger.error("Error querying Algolia for listing %s: %s", cleaned_id, exc)
            return None, None

    async def get_seller_by_username(
        self, username: str, session: aiohttp.ClientSession
    ) -> SellerData | None:
        """Fetch seller profile data by username via Algolia search."""
        cleaned_username = username.strip()
        payload = {
            "requests": [
                {
                    "indexName": self.cfg.index_name,
                    "params": f"query={cleaned_username}&hitsPerPage=1",
                }
            ]
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.cfg.timeout_sec)
            async with session.post(
                self._get_endpoint_url(),
                headers=self._get_headers(),
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    if results and results[0].get("hits"):
                        hit = results[0]["hits"][0]
                        user_data = hit.get("user") or {}
                        hit_username = user_data.get("username", "")
                        if hit_username.lower() == cleaned_username.lower():
                            _, seller_data = self._map_hit_to_models(hit)
                            return seller_data

                    logger.info("Seller username %s not found in Algolia hits", cleaned_username)
                    return None
                else:
                    err_body = await resp.text()
                    logger.error(
                        "Algolia seller query failed with HTTP %s for %s: %s",
                        resp.status,
                        cleaned_username,
                        err_body[:200],
                    )
                    return None

        except TimeoutError:
            logger.warning("Algolia seller query timed out for %s", cleaned_username)
            return None
        except Exception as exc:
            logger.error("Error querying Algolia for seller %s: %s", cleaned_username, exc)
            return None


grailed_algolia_client = GrailedAlgoliaClient()

__all__ = ["GrailedAlgoliaClient", "grailed_algolia_client"]
