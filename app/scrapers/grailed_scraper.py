"""Grailed scraper implementing the unified ScraperProtocol interface.

Provides Grailed-specific implementation of item and seller data extraction
with consistent interface for use in the scraping orchestrator.
"""

import json
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from ..models import ItemData, SellerData
from .base import BaseScraper
from .grailed_url_resolver import normalize_grailed_url
from .headless import get_grailed_seller_data_headless

logger = logging.getLogger(__name__)

PRICE_RE = re.compile(r"^\d[\d,.]*$")


def _clean_price(raw: str) -> Decimal | None:
    """Clean and parse price string."""
    raw = raw.strip()
    if not PRICE_RE.match(raw):
        return None
    try:
        return Decimal(raw.replace(",", ""))
    except Exception:
        return None


def _parse_json_ld(soup: BeautifulSoup) -> Decimal | None:
    """Parse JSON-LD structured data for price."""
    for script in soup.find_all("script", type="application/ld+json"):
        text = script.string
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue

        offers = data.get("offers") or data.get("@graph", [])
        price_val = None

        if isinstance(offers, dict):
            price_val = offers.get("price")
        elif isinstance(offers, list):
            for item in offers:
                if isinstance(item, dict) and item.get("price"):
                    price_val = item["price"]
                    break

        if price_val is not None:
            price = _clean_price(str(price_val))
            if price:
                return price
    return None


def _parse_next_data(soup: BeautifulSoup) -> dict[str, Any] | None:
    """Parse Next.js __NEXT_DATA__ for modern Grailed listings.

    Grailed now uses Next.js architecture where listing data is embedded
    in a <script id="__NEXT_DATA__"> tag as JSON.

    Returns:
        Dictionary containing listing data or None if not found/invalid.
    """
    try:
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return None

        data = json.loads(script.string)

        # Navigate to listing data: props.pageProps.listing
        props = data.get("props", {})
        page_props = props.get("pageProps", {})
        listing = page_props.get("listing", {})

        if listing:
            return listing

    except (json.JSONDecodeError, KeyError, AttributeError):
        pass

    return None


def _scrape_shipping_grailed(soup: BeautifulSoup) -> Decimal | None:
    """Extract Grailed shipping cost."""
    # First try Next.js data (modern Grailed listings)
    next_data = _parse_next_data(soup)
    if next_data:
        shipping_data = next_data.get("shipping", {})
        if isinstance(shipping_data, dict):
            us_shipping = shipping_data.get("us", {})
            if isinstance(us_shipping, dict):
                amount = us_shipping.get("amount")
                if amount:
                    # Remove $ and clean price
                    clean_amount = str(amount).replace("$", "").strip()
                    shipping_price = _clean_price(clean_amount)
                    if shipping_price is not None:
                        return shipping_price

    # Fallback to legacy methods
    # Look for shipping text
    shipping_text = soup.find(string=re.compile(r"shipping", re.I))
    if shipping_text:
        parent = shipping_text.parent
        if parent:
            text = parent.get_text()
            if "free" in text.lower():
                return Decimal("0")
            shipping_match = re.search(r"\$(\d+(?:\.\d{2})?)", text)
            if shipping_match:
                return Decimal(shipping_match.group(1))

    # Look for shipping div
    shipping_elem = soup.find("div", string=re.compile(r"shipping", re.I))
    if shipping_elem:
        next_elem = shipping_elem.find_next_sibling()
        if next_elem:
            text = next_elem.get_text(strip=True)
            if "free" in text.lower():
                return Decimal("0")
            shipping_match = re.search(r"\$(\d+(?:\.\d{2})?)", text)
            if shipping_match:
                return Decimal(shipping_match.group(1))

    # Default Grailed shipping
    return Decimal("15")


def _extract_title(soup: BeautifulSoup) -> str | None:
    """Extract item title."""
    # First try Next.js data (modern Grailed listings)
    next_data = _parse_next_data(soup)
    if next_data:
        title = next_data.get("title")
        if title:
            return str(title).strip()

    # Fallback to legacy methods
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"]
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


def _extract_image_url(soup: BeautifulSoup) -> str | None:
    """Extract primary product image URL.

    Extracts the main product image URL from Grailed listing for display
    in bot messages. Prioritizes Next.js data over meta tags.

    Returns:
        str: Image URL or None if not found.
    """
    # First try Next.js data (modern Grailed listings)
    next_data = _parse_next_data(soup)
    if next_data:
        # Check various possible image field names
        image_fields = ["images", "photos", "image", "photo", "mainImage"]
        for field in image_fields:
            images = next_data.get(field, [])
            if images:
                if isinstance(images, list) and len(images) > 0:
                    # Return first image from list
                    first_image = images[0]
                    if isinstance(first_image, dict):
                        # Handle image object with URL field
                        return first_image.get("url") or first_image.get("src")
                    elif isinstance(first_image, str):
                        # Direct URL string
                        return first_image
                elif isinstance(images, str):
                    # Single image URL
                    return images

    # Fallback to meta tags
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return og_image["content"]

    # Try Twitter card image
    twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
    if twitter_image and twitter_image.get("content"):
        return twitter_image["content"]

    # Try first img tag with data-src or src
    img_tag = soup.find("img", attrs={"data-src": True}) or soup.find("img", src=True)
    if img_tag:
        return img_tag.get("data-src") or img_tag.get("src")

    return None


def _extract_price_and_buyability(url: str, soup: BeautifulSoup) -> tuple[Decimal | None, bool]:
    """Extract price and determine if item is buyable."""
    # First try Next.js data (modern Grailed listings)
    price = None
    is_buyable = False

    next_data = _parse_next_data(soup)
    if next_data:
        price_str = next_data.get("price")
        if price_str:
            clean_price_str = str(price_str).replace("$", "").strip()
            price = _clean_price(clean_price_str)

        buy_now_price = next_data.get("buyNowPrice")
        has_buy_now_price = next_data.get("hasBuyNowPrice")
        purchase_type = str(next_data.get("purchaseType") or "").lower()
        sell_style = str(next_data.get("sellStyle") or "").lower()

        is_buyable = bool(buy_now_price or has_buy_now_price)
        if purchase_type in {"buy_it_now", "buy_now"} or sell_style in {"buy_it_now", "buy_now"}:
            is_buyable = True

        buy_now_flag = next_data.get("buyNow")
        if isinstance(buy_now_flag, bool):
            if buy_now_flag:
                is_buyable = True
            else:
                is_buyable = False

        status_text = str(next_data.get("status") or "").lower()
        make_offer = bool(next_data.get("makeOffer"))
        if not is_buyable and ("offer" in status_text or make_offer):
            is_buyable = False

    # Fallback to legacy methods if Next.js data not found
    if price is None:
        span = soup.find("span", attrs={"class": lambda c: c and "price" in c.lower()})
        if span:
            price = _clean_price(span.get_text(strip=True))
        if not price:
            meta = soup.find("meta", property="product:price:amount")
            if meta and meta.get("content"):
                price = _clean_price(meta["content"])
        if not price:
            price = _parse_json_ld(soup)

        # Legacy buyability check
        try:
            for script in soup.find_all("script"):
                if script.string and "buyNow" in script.string:
                    buy_now_match = re.search(r'"buyNow"\s*:\s*(true|false)', script.string)
                    if buy_now_match:
                        is_buyable = buy_now_match.group(1) == "true"
                        break
        except Exception:
            is_buyable = price is not None

    return price, is_buyable


class GrailedScraper(BaseScraper):
    """Grailed scraper implementing ScraperProtocol.

    Wraps existing Grailed scraping functionality in a standardized interface
    that can be used polymorphically with other marketplace scrapers.

    Features:
    - Item data extraction from Grailed listings
    - Seller data extraction from Grailed profiles
    - URL validation for Grailed domains
    - Seller profile URL extraction from item data
    - Support for both Next.js and legacy Grailed formats
    """

    def __init__(self):
        """Initialize Grailed scraper."""
        super().__init__("grailed")
        self._cached_seller_data = None

    async def scrape_item(self, url: str, session: aiohttp.ClientSession) -> ItemData | None:
        """Extract item data from Grailed listing URL.

        Args:
            url: Grailed item listing URL.
            session: HTTP session for requests.

        Returns:
            ItemData object if successful, None if failed.
        """
        self._log_scraping_start(url, "item")

        normalized_url = normalize_grailed_url(url)
        if normalized_url != url:
            self.logger.debug("Normalized Grailed URL %s → %s", url, normalized_url)
            url = normalized_url

        try:
            async with session.get(url) as response:
                response.raise_for_status()

                # Check Content-Type to avoid parsing JSON as HTML
                content_type = response.headers.get("content-type", "").lower()
                if "application/json" in content_type:
                    # Server returned JSON instead of HTML - listing may be unavailable
                    return None

                html = await response.text()

                # Additional validation: check if response looks like a listing page
                if not html or len(html) < 1000:
                    # Response too short to be a valid listing page
                    return None

        except Exception:
            return None

        soup = BeautifulSoup(html, "lxml")

        # Extract price and buyability
        price, is_buyable = _extract_price_and_buyability(url, soup)

        # Extract shipping
        shipping = _scrape_shipping_grailed(soup)

        # Extract title
        title = _extract_title(soup)

        # Extract image URL
        image_url = _extract_image_url(soup)

        # Extract seller data
        seller_data = await self._extract_seller_data(soup, session)

        item_data = ItemData(
            price=price,
            shipping_us=shipping,
            is_buyable=is_buyable,
            title=title,
            image_url=image_url,
        )

        if item_data:
            self._log_scraping_success(url, "item", f"'{item_data.title}' - ${item_data.price}")
            self._cached_seller_data = seller_data
            return item_data
        else:
            self.logger.warning(f"No item data extracted from Grailed URL: {url}")
            return None

    async def scrape_seller(self, url: str, session: aiohttp.ClientSession) -> SellerData | None:
        """Extract seller data from Grailed profile URL.

        Args:
            url: Grailed seller profile URL.
            session: HTTP session for requests.

        Returns:
            SellerData object if successful, None if failed.
        """
        self._log_scraping_start(url, "seller")

        normalized_url = normalize_grailed_url(url)
        if normalized_url != url:
            self.logger.debug("Normalized Grailed seller URL %s → %s", url, normalized_url)
            url = normalized_url

        # Check for cached seller data first
        if self._cached_seller_data and url == "https://www.grailed.com/cached_seller":
            seller_data = self._cached_seller_data
            self._cached_seller_data = None  # Clear cache after use
            trusted_status = "trusted" if seller_data.trusted_badge else "standard"
            self._log_scraping_success(
                url,
                "seller",
                f"Rating: {seller_data.avg_rating:.1f}, Reviews: {seller_data.num_reviews}, Status: {trusted_status}",
            )
            return seller_data

        try:
            # Используем оптимизированный headless browser для всех профилей
            seller_data = await get_grailed_seller_data_headless(url)

            if seller_data:
                trusted_status = "trusted" if seller_data.trusted_badge else "standard"
                self._log_scraping_success(
                    url,
                    "seller",
                    f"Rating: {seller_data.avg_rating:.1f}, Reviews: {seller_data.num_reviews}, Status: {trusted_status}",
                )
                return seller_data
            self.logger.warning(f"No seller data extracted from Grailed profile: {url}")
            return _fallback_seller_data("no_metrics_extracted")

        except Exception as e:
            self._log_scraping_error(url, "seller", e)
            return _fallback_seller_data("headless_error")

    def supports_url(self, url: str) -> bool:
        """Check if URL is from Grailed."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().split(":")[0]
            return "grailed" in domain.split(".")
        except Exception:
            return False

    def is_seller_profile(self, url: str) -> bool:
        """Check if URL is a Grailed seller profile."""
        try:
            parsed = urlparse(url)
            if "grailed.com" not in parsed.netloc.lower():
                return False

            path = parsed.path.lower().strip("/")

            # Direct username pattern
            if path and "/" not in path and not path.startswith("listings"):
                excluded_pages = {
                    "sell",
                    "buy",
                    "search",
                    "help",
                    "about",
                    "terms",
                    "privacy",
                    "brands",
                    "designers",
                    "categories",
                    "login",
                    "signup",
                    "settings",
                    "notifications",
                    "feed",
                }
                if path not in excluded_pages:
                    return True

            # Legacy patterns
            if path.startswith("users/") or path.startswith("sellers/") or path.startswith("user/"):
                return True

            return False
        except Exception:
            return False

    def extract_seller_profile_url(self, item_data: ItemData) -> str | None:
        """Extract seller profile URL from Grailed item data."""
        try:
            # If we have cached seller data, return a dummy URL to trigger scrape_seller
            if self._cached_seller_data:
                return "https://www.grailed.com/cached_seller"
            else:
                self.logger.info("No cached seller data available")
                return None
        except Exception as e:
            self.logger.error(f"Failed to extract seller profile URL: {e}")
            return None

    async def _extract_seller_data(
        self, soup: BeautifulSoup, session: aiohttp.ClientSession
    ) -> SellerData | None:
        """Extract seller data using headless browser only."""
        try:
            # Get seller profile URL first
            profile_url = self._extract_seller_profile_url_from_soup(soup)
            logger.debug(f"Extracted profile URL: {profile_url}")

            if not profile_url:
                logger.warning("No seller profile URL found in listing")
                return None

            return await self.scrape_seller(profile_url, session)

        except Exception as e:
            logger.error(f"Error extracting seller data: {e}")
            return None

    def _extract_seller_profile_url_from_soup(self, soup: BeautifulSoup) -> str | None:
        """Extract seller profile URL from listing page."""
        try:
            # Try JSON data first - expanded patterns
            for script in soup.find_all("script"):
                if not script.string:
                    continue

                script_content = script.string
                if any(
                    keyword in script_content.lower()
                    for keyword in ["seller", "user", "owner", "profile"]
                ):
                    # Extended username patterns with more comprehensive coverage
                    username_patterns = [
                        # Direct seller/user object patterns
                        r'"(?:seller|user|owner)"\s*:\s*\{[^}]*"username"\s*:\s*"([^"]+)"'
                    ]

                    for pattern in username_patterns:
                        username_match = re.search(pattern, script_content, re.IGNORECASE)
                        if username_match:
                            username = username_match.group(1).strip()
                            if username and len(username) > 2:
                                logger.debug(f"Found username: {username}")
                                return f"https://www.grailed.com/{username}"
            return None
        except Exception as e:
            logger.error(f"Error extracting seller profile URL: {e}")
            return None


# Create and export Grailed scraper instance
grailed_scraper = GrailedScraper()


def _fallback_seller_data(reason: str) -> SellerData:
    """Return safe default seller payload when extraction fails."""
    logger.warning("Using fallback seller data due to: %s", reason)
    return SellerData(
        num_reviews=0,
        avg_rating=0.0,
        trusted_badge=False,
        last_updated=datetime.now(UTC),
        technical_issue=True,
    )
