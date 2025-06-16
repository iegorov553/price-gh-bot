"""Grailed listing scraper and seller profile analyzer.

This module handles scraping Grailed marketplace listings for item data, shipping costs,
and buyability detection. It also provides comprehensive seller profile analysis including
rating evaluation, review count tracking, trusted badge detection, and activity monitoring.

Key features:
- Item price and shipping cost extraction with multiple fallback strategies
- Buyability detection for buy-now vs offer-only listings
- Comprehensive seller reliability analysis and scoring
- Robust JSON and HTML parsing with error handling
- Profile URL extraction and seller activity tracking
"""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from ..models import ItemData, SellerData

PRICE_RE = re.compile(r"^\d[\d,.]*$")


def _clean_price(raw: str) -> Decimal | None:
    """Clean and parse price string."""
    raw = raw.strip()
    if not PRICE_RE.match(raw):
        return None
    try:
        return Decimal(raw.replace(',', ''))
    except Exception:
        return None


def _parse_json_ld(soup: BeautifulSoup) -> Decimal | None:
    """Parse JSON-LD structured data for price."""
    for script in soup.find_all('script', type='application/ld+json'):
        text = script.string
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue

        offers = data.get('offers') or data.get('@graph', [])
        price_val = None

        if isinstance(offers, dict):
            price_val = offers.get('price')
        elif isinstance(offers, list):
            for item in offers:
                if isinstance(item, dict) and item.get('price'):
                    price_val = item['price']
                    break

        if price_val is not None:
            price = _clean_price(str(price_val))
            if price:
                return price
    return None


def _scrape_shipping_grailed(soup: BeautifulSoup) -> Decimal | None:
    """Extract Grailed shipping cost."""
    # Look for shipping text
    shipping_text = soup.find(string=re.compile(r'shipping', re.I))
    if shipping_text:
        parent = shipping_text.parent
        if parent:
            text = parent.get_text()
            if 'free' in text.lower():
                return Decimal('0')
            shipping_match = re.search(r'\$(\d+(?:\.\d{2})?)', text)
            if shipping_match:
                return Decimal(shipping_match.group(1))

    # Look for shipping div
    shipping_elem = soup.find('div', string=re.compile(r'shipping', re.I))
    if shipping_elem:
        next_elem = shipping_elem.find_next_sibling()
        if next_elem:
            text = next_elem.get_text(strip=True)
            if 'free' in text.lower():
                return Decimal('0')
            shipping_match = re.search(r'\$(\d+(?:\.\d{2})?)', text)
            if shipping_match:
                return Decimal(shipping_match.group(1))

    # Default Grailed shipping
    return Decimal('15')


def _extract_title(soup: BeautifulSoup) -> str | None:
    """Extract item title."""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"]
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


def _extract_price_and_buyability(url: str, soup: BeautifulSoup) -> tuple[Decimal | None, bool]:
    """Extract price and determine if item is buyable."""
    # Extract price
    price = None
    span = soup.find('span', attrs={'class': lambda c: c and 'price' in c.lower()})
    if span:
        price = _clean_price(span.get_text(strip=True))
    if not price:
        meta = soup.find('meta', property='product:price:amount')
        if meta and meta.get('content'):
            price = _clean_price(meta['content'])
    if not price:
        price = _parse_json_ld(soup)

    # Check buyability from JSON data
    is_buyable = False
    try:
        for script in soup.find_all('script'):
            if script.string and 'buyNow' in script.string:
                buy_now_match = re.search(r'"buyNow"\s*:\s*(true|false)', script.string)
                if buy_now_match:
                    is_buyable = buy_now_match.group(1) == 'true'
                    break
    except Exception:
        # Fallback: assume buyable if price is found
        is_buyable = price is not None

    return price, is_buyable


def _extract_seller_profile_url(soup: BeautifulSoup) -> str | None:
    """Extract seller profile URL from listing page."""
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Try JSON data first - expanded patterns
        for script in soup.find_all('script'):
            if not script.string:
                continue

            script_content = script.string
            if any(keyword in script_content.lower() for keyword in ['seller', 'user', 'owner', 'profile']):

                # Extended username patterns with more comprehensive coverage
                username_patterns = [
                    # Direct seller/user object patterns
                    r'"(?:seller|user|owner)"\s*:\s*\{[^}]*"username"\s*:\s*"([^"]+)"',
                    r'"username"\s*:\s*"([^"]+)"[^}]*"(?:seller|user|owner)"',
                    r'"(?:sellerName|userName|ownerName|sellerUsername)"\s*:\s*"([^"]+)"',
                    r'"name"\s*:\s*"([^"]+)"[^}]*"(?:seller|user)"',

                    # Nested object patterns
                    r'seller["\s]*:[^{]*{[^}]*username["\s]*:["\s]*([^"]+)',
                    r'user["\s]*:[^{]*{[^}]*username["\s]*:["\s]*([^"]+)',
                    r'owner["\s]*:[^{]*{[^}]*username["\s]*:["\s]*([^"]+)',

                    # Alternative structures
                    r'"seller"\s*:\s*"([^"]+)"',  # Direct seller string
                    r'"sellerSlug"\s*:\s*"([^"]+)"',
                    r'"userSlug"\s*:\s*"([^"]+)"',

                    # Profile path patterns in JSON
                    r'"(?:profilePath|userPath|sellerPath)"\s*:\s*"/?([^"]+)"',
                    r'"/([^/"]+)"\s*.*"(?:seller|user|profile)"',
                ]

                for pattern in username_patterns:
                    username_match = re.search(pattern, script_content, re.IGNORECASE)
                    if username_match:
                        username = username_match.group(1).strip()
                        if username and len(username) > 2:
                            logger.debug(f"Found username: {username}")
                            return f"https://www.grailed.com/{username}"

                # Direct profile URL patterns
                url_patterns = [
                    r'"(?:profileUrl|userUrl|sellerUrl|profile_url)"\s*:\s*"([^"]+)"',
                    r'"url"\s*:\s*"([^"]*(?:/users/|/sellers/|grailed\.com/)[^"]*)"',
                    r'href\s*=\s*["\']([^"\']*(?:/users/|/sellers/)[^"\']*)["\']',
                ]

                for pattern in url_patterns:
                    profile_match = re.search(pattern, script_content, re.IGNORECASE)
                    if profile_match:
                        url = profile_match.group(1).strip()
                        if url:
                            if url.startswith('/'):
                                return f"https://www.grailed.com{url}"
                            elif 'grailed.com' in url:
                                return url

        # HTML link fallbacks - comprehensive search
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').strip()
            text = link.get_text(strip=True).lower()
            classes = ' '.join(link.get('class', [])).lower()

            # Direct profile URL patterns
            if any(pattern in href for pattern in ['/users/', '/sellers/', '/user/', '/seller/']):
                if href.startswith('/'):
                    return f"https://www.grailed.com{href}"
                elif href.startswith('https://www.grailed.com/'):
                    return href

            # Username-only URLs (most common pattern)
            if href.startswith('/') and href.count('/') == 1:
                username = href.strip('/')
                excluded_paths = {
                    'listings', 'search', 'sell', 'buy', 'help', 'about', 'terms',
                    'privacy', 'brands', 'designers', 'categories', 'login', 'signup',
                    'settings', 'notifications', 'feed', 'api', 'static', 'assets'
                }
                if username and username not in excluded_paths and len(username) > 1:
                    # Additional validation - check if this looks like a username
                    if re.match(r'^[a-zA-Z0-9_.-]+$', username):
                        return f"https://www.grailed.com{href}"

            # Check for seller indicators in link text or classes
            seller_indicators = ['seller', 'user', 'profile', 'shop', 'by ', 'from ']
            if any(indicator in text or indicator in classes for indicator in seller_indicators):
                if href.startswith('/') and href.count('/') <= 2:
                    parts = href.strip('/').split('/')
                    if len(parts) >= 1 and parts[0] not in excluded_paths:
                        return f"https://www.grailed.com{href}"

        # Look for profile links in specific HTML structures
        profile_selectors = [
            'a[href*="/user"]', 'a[href*="/seller"]', 'a[href*="profile"]',
            '.seller-link', '.user-link', '.profile-link',
            'a.seller', 'a.user', '[data-seller]', '[data-user]'
        ]

        for selector in profile_selectors:
            try:
                elements = soup.select(selector)
                for element in elements:
                    href = element.get('href', '').strip()
                    if href:
                        if href.startswith('/'):
                            return f"https://www.grailed.com{href}"
                        elif 'grailed.com' in href:
                            return href
            except Exception:
                continue

        logger.debug("No seller profile URL found")
        return None

    except Exception as e:
        logger.error(f"Error extracting seller profile URL: {e}")
        return None


async def _fetch_seller_last_update(profile_url: str, session: aiohttp.ClientSession) -> datetime | None:
    """Fetch seller's last update date from profile."""
    try:
        async with session.get(profile_url) as response:
            response.raise_for_status()
            html = await response.text()

        soup = BeautifulSoup(html, 'lxml')
        latest_date = None

        # Look for dates in JSON scripts
        for script in soup.find_all('script'):
            if not script.string:
                continue

            script_content = script.string
            if any(keyword in script_content for keyword in ['date', 'time', 'created', 'updated']):
                date_patterns = [
                    r'"(?:updatedAt|lastUpdated|dateUpdated)"\s*:\s*"([^"]+)"',
                    r'"(?:createdAt|dateCreated|created)"\s*:\s*"([^"]+)"',
                    r'"(?:publishedAt|datePublished)"\s*:\s*"([^"]+)"',
                    r'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))"',
                    r'"(?:time|date)"\s*:\s*(\d{10,13})',
                ]

                for pattern in date_patterns:
                    for date_str in re.findall(pattern, script_content, re.IGNORECASE):
                        try:
                            if date_str.isdigit():
                                timestamp = int(date_str)
                                if timestamp > 1000000000000:
                                    timestamp = timestamp / 1000
                                date_obj = datetime.fromtimestamp(timestamp, tz=UTC)
                            elif 'T' in date_str:
                                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            else:
                                date_obj = datetime.fromisoformat(date_str)
                                if date_obj.tzinfo is None:
                                    date_obj = date_obj.replace(tzinfo=UTC)

                            if latest_date is None or date_obj > latest_date:
                                latest_date = date_obj
                        except Exception:
                            continue

        return latest_date
    except Exception:
        return None


async def _extract_seller_data(soup: BeautifulSoup, session: aiohttp.ClientSession) -> SellerData | None:
    """Extract seller data using headless browser only.

    Static HTML parsing from Grailed profile pages doesn't work due to React SPA architecture.
    Only headless browser can execute JavaScript to access dynamically loaded seller data.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Get seller profile URL first
        profile_url = _extract_seller_profile_url(soup)
        logger.debug(f"Extracted profile URL: {profile_url}")

        if not profile_url:
            logger.warning("No seller profile URL found in listing")
            return None

        # Use headless browser to extract seller data
        from ..config import config
        if config.bot.enable_headless_browser:
            logger.info("Using headless browser to extract seller data")
            try:
                from .headless import get_grailed_seller_data_headless
                headless_data = await get_grailed_seller_data_headless(profile_url)
                if headless_data:
                    # Try to get more accurate last update time using profile analysis
                    try:
                        profile_last_update = await _fetch_seller_last_update(profile_url, session)
                        if profile_last_update:
                            # Update the headless data with more accurate timestamp
                            headless_data = SellerData(
                                num_reviews=headless_data.num_reviews,
                                avg_rating=headless_data.avg_rating,
                                trusted_badge=headless_data.trusted_badge,
                                last_updated=profile_last_update
                            )
                            logger.debug(f"Updated headless data with profile timestamp: {profile_last_update}")
                    except Exception as e:
                        logger.debug(f"Failed to get profile timestamp, using headless timestamp: {e}")

                    logger.info(f"Successfully extracted seller data with headless browser: {headless_data}")
                    return headless_data
                else:
                    logger.warning("Headless browser failed to find seller data")
            except ImportError:
                logger.warning("Playwright not available - install with: pip install playwright")
            except Exception as e:
                logger.warning(f"Headless browser extraction failed: {e}")
        else:
            logger.debug("Headless browser disabled in configuration")

        # Return empty seller data for "No Data" category
        # Static HTML extraction doesn't work due to React SPA architecture
        seller_data = SellerData(
            num_reviews=0,
            avg_rating=0.0,
            trusted_badge=False,
            last_updated=datetime.now(UTC)
        )

        logger.warning("No seller metrics available - Grailed uses React SPA with client-side data loading")
        return seller_data

    except Exception as e:
        logger.error(f"Error extracting seller data: {e}")
        return None


async def get_item_data(url: str, session: aiohttp.ClientSession) -> tuple[ItemData, SellerData | None]:
    """Scrape Grailed item data and seller information.

    Extracts comprehensive item data including price, shipping costs, buyability status,
    and title. Also analyzes seller profile for reliability metrics including rating,
    review count, trusted badge status, and last activity.

    Args:
        url: Grailed listing URL to scrape
        session: aiohttp ClientSession for making HTTP requests

    Returns:
        Tuple containing ItemData object and optional SellerData object.
        ItemData includes price, shipping, buyability, and title.
        SellerData includes rating, reviews, badge status, and last update.
    """
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            
            # Check Content-Type to avoid parsing JSON as HTML
            content_type = response.headers.get('content-type', '').lower()
            if 'application/json' in content_type:
                # Server returned JSON instead of HTML - listing may be unavailable
                return ItemData(), None
            
            html = await response.text()
            
            # Additional validation: check if response looks like a listing page
            if not html or len(html) < 1000:
                # Response too short to be a valid listing page
                return ItemData(), None
                
    except Exception:
        return ItemData(), None

    soup = BeautifulSoup(html, 'lxml')

    # Extract price and buyability
    price, is_buyable = _extract_price_and_buyability(url, soup)

    # Extract shipping
    shipping = _scrape_shipping_grailed(soup)

    # Extract title
    title = _extract_title(soup)

    # Extract seller data
    seller_data = await _extract_seller_data(soup, session)

    item_data = ItemData(
        price=price,
        shipping_us=shipping,
        is_buyable=is_buyable,
        title=title
    )

    return item_data, seller_data


def is_grailed_url(url: str) -> bool:
    """Check if URL is a Grailed listing.

    Validates whether a given URL belongs to the Grailed marketplace domain.
    Used to route URLs to the appropriate scraper.

    Args:
        url: URL string to validate

    Returns:
        True if URL is from Grailed domain, False otherwise
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().split(':')[0]
        return 'grailed' in domain.split('.')
    except Exception:
        return False


def is_grailed_seller_profile(url: str) -> bool:
    """Check if URL is a Grailed seller profile.

    Determines if a URL points to a Grailed seller profile page rather than
    a listing. Supports various profile URL formats including direct usernames
    and legacy /users/ paths.

    Args:
        url: URL string to check

    Returns:
        True if URL is a Grailed seller profile, False otherwise
    """
    try:
        parsed = urlparse(url)
        if 'grailed.com' not in parsed.netloc.lower():
            return False

        path = parsed.path.lower().strip('/')

        # Direct username pattern
        if path and '/' not in path and not path.startswith('listings'):
            excluded_pages = {
                'sell', 'buy', 'search', 'help', 'about', 'terms',
                'privacy', 'brands', 'designers', 'categories', 'login',
                'signup', 'settings', 'notifications', 'feed'
            }
            if path not in excluded_pages:
                return True

        # Legacy patterns
        if path.startswith('users/') or path.startswith('sellers/') or path.startswith('user/'):
            return True

        return False
    except Exception:
        return False


async def analyze_seller_profile(profile_url: str, session: aiohttp.ClientSession) -> dict[str, Any] | None:
    """Analyze Grailed seller profile for reliability metrics.

    Uses headless browser to extract seller data that is loaded dynamically
    via JavaScript on profile pages. Falls back to minimal data if extraction fails.

    Args:
        profile_url: Grailed seller profile URL to analyze
        session: aiohttp ClientSession for making HTTP requests

    Returns:
        Dictionary containing seller metrics:
        - num_reviews: Number of seller reviews (extracted via headless browser)
        - avg_rating: Average seller rating (extracted via headless browser)
        - trusted_badge: Whether seller has trusted badge (extracted via headless browser)
        - last_updated: Current timestamp
        Returns minimal data if extraction fails.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Try headless browser extraction first if enabled
    from ..config import config
    if config.bot.enable_headless_browser:
        try:
            from .headless import get_grailed_seller_data_headless
            logger.debug(f"Analyzing profile with optimized headless browser: {profile_url}")

            headless_data = await get_grailed_seller_data_headless(profile_url)
            if headless_data:
                logger.info(f"Successfully extracted profile data with headless browser: {headless_data}")
                return {
                    'num_reviews': headless_data.num_reviews,
                    'avg_rating': headless_data.avg_rating,
                    'trusted_badge': headless_data.trusted_badge,
                    'last_updated': headless_data.last_updated
                }
            else:
                logger.warning(f"Headless browser found no data for profile: {profile_url}")

        except ImportError:
            logger.warning("Playwright not available for profile analysis - install with: pip install playwright")
        except Exception as e:
            logger.warning(f"Headless browser profile analysis failed: {e}")
    else:
        logger.debug("Headless browser disabled in configuration")

    # Fallback to minimal data
    logger.debug(f"Returning minimal data for profile: {profile_url}")
    return {
        'num_reviews': 0,
        'avg_rating': 0.0,
        'trusted_badge': False,
        'last_updated': datetime.now(UTC)
    }


async def check_grailed_availability(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Check if Grailed website is available and responsive.

    Tests Grailed's main page and API endpoints to determine if the site
    is experiencing downtime or technical issues. Used for better error
    reporting when individual listing scraping fails.

    Args:
        session: aiohttp ClientSession for making HTTP requests

    Returns:
        Dictionary containing availability status:
        - is_available: True if Grailed is responsive, False otherwise
        - status_code: HTTP status code from main page check
        - response_time_ms: Response time in milliseconds
        - error_message: Description of any errors encountered
    """
    import logging
    import time

    logger = logging.getLogger(__name__)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }

    start_time = time.time()

    try:
        # Try main page first
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(
            'https://www.grailed.com',
            headers=headers,
            timeout=timeout
        ) as response:
            response_time_ms = int((time.time() - start_time) * 1000)

            if response.status == 200:
                logger.debug(f"Grailed main page accessible: {response.status} in {response_time_ms}ms")
                return {
                    'is_available': True,
                    'status_code': response.status,
                    'response_time_ms': response_time_ms,
                    'error_message': None
                }
            else:
                logger.warning(f"Grailed main page returned non-200 status: {response.status}")
                return {
                    'is_available': False,
                    'status_code': response.status,
                    'response_time_ms': response_time_ms,
                    'error_message': f"HTTP {response.status} error from main page"
                }

    except TimeoutError:
        response_time_ms = int((time.time() - start_time) * 1000)
        logger.warning(f"Grailed availability check timed out after {response_time_ms}ms")
        return {
            'is_available': False,
            'status_code': None,
            'response_time_ms': response_time_ms,
            'error_message': "Connection timeout - site may be slow or unavailable"
        }

    except aiohttp.ClientError as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Network error checking Grailed availability: {e}")
        return {
            'is_available': False,
            'status_code': None,
            'response_time_ms': response_time_ms,
            'error_message': f"Network error: {str(e)}"
        }

    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Unexpected error checking Grailed availability: {e}")
        return {
            'is_available': False,
            'status_code': None,
            'response_time_ms': response_time_ms,
            'error_message': f"Unexpected error: {str(e)}"
        }
