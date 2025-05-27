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

                # Extended username patterns
                username_patterns = [
                    r'"(?:seller|user|owner)"\s*:\s*\{[^}]*"username"\s*:\s*"([^"]+)"',
                    r'"username"\s*:\s*"([^"]+)"[^}]*"(?:seller|user|owner)"',
                    r'"(?:sellerName|userName|ownerName)"\s*:\s*"([^"]+)"',
                    r'"name"\s*:\s*"([^"]+)"[^}]*"(?:seller|user)"',
                    r'seller["\s]*:[^{]*{[^}]*username["\s]*:["\s]*([^"]+)',
                    r'user["\s]*:[^{]*{[^}]*username["\s]*:["\s]*([^"]+)',
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

        # HTML link fallbacks - improved patterns
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').strip()
            text = link.get_text(strip=True).lower()

            # Check href patterns
            if any(pattern in href for pattern in ['/users/', '/sellers/', '/user/']):
                if href.startswith('/'):
                    return f"https://www.grailed.com{href}"
                elif href.startswith('https://www.grailed.com/'):
                    return href

            # Check for seller/user links in text
            if any(keyword in text for keyword in ['seller', 'user', 'profile', 'shop']):
                if href.startswith('/') and href.count('/') >= 2:
                    parts = href.strip('/').split('/')
                    if len(parts) == 1 and not any(exclude in parts[0] for exclude in
                        ['listings', 'search', 'sell', 'buy', 'help', 'about', 'terms', 'privacy']):
                        return f"https://www.grailed.com{href}"

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
    """Extract seller data from listing page."""
    import logging
    logger = logging.getLogger(__name__)

    try:
        avg_rating = 0.0
        num_reviews = 0
        trusted_badge = False

        # Get seller profile URL first
        profile_url = _extract_seller_profile_url(soup)
        logger.debug(f"Extracted profile URL: {profile_url}")

        if not profile_url:
            logger.warning("No seller profile URL found in listing")
            return None

        # Look for seller data in listing JSON - enhanced patterns for modern Grailed structure
        for script in soup.find_all('script'):
            if not script.string:
                continue

            script_content = script.string

            # First try to parse preloaded state JSON
            if 'window.__PRELOADED_STATE__' in script_content:
                json_match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});?$', script_content, re.MULTILINE | re.DOTALL)
                if json_match:
                    try:
                        import json
                        json_data = json.loads(json_match.group(1))

                        # Navigate through typical Grailed JSON structure
                        seller_data = None
                        if 'listing' in json_data and isinstance(json_data['listing'], dict):
                            listing = json_data['listing']
                            if 'seller' in listing:
                                seller_data = listing['seller']
                            elif 'user' in listing:
                                seller_data = listing['user']

                        if seller_data and isinstance(seller_data, dict):
                            # Extract rating
                            for rating_key in ['rating', 'averageRating', 'avg_rating', 'sellerRating']:
                                if rating_key in seller_data:
                                    try:
                                        rating_val = float(seller_data[rating_key])
                                        if 0 <= rating_val <= 5:
                                            avg_rating = rating_val
                                            logger.debug(f"Found rating from JSON: {avg_rating}")
                                            break
                                    except (ValueError, TypeError):
                                        continue

                            # Extract review count
                            for review_key in ['reviewCount', 'totalReviews', 'reviews', 'numReviews', 'review_count']:
                                if review_key in seller_data:
                                    try:
                                        review_val = int(seller_data[review_key])
                                        if review_val >= 0:
                                            num_reviews = review_val
                                            logger.debug(f"Found review count from JSON: {num_reviews}")
                                            break
                                    except (ValueError, TypeError):
                                        continue

                            # Extract trusted badge
                            for trusted_key in ['trusted', 'trustedSeller', 'isTrusted', 'verified', 'verifiedSeller']:
                                if trusted_key in seller_data and seller_data[trusted_key]:
                                    trusted_badge = True
                                    logger.debug("Found trusted badge from JSON")
                                    break

                        if avg_rating > 0 or num_reviews > 0 or trusted_badge:
                            break  # Found data, no need to continue

                    except json.JSONDecodeError:
                        pass  # Fall back to regex patterns

            # Fallback: enhanced regex patterns for seller data
            if (avg_rating == 0.0 and num_reviews == 0 and not trusted_badge and
                any(keyword in script_content.lower() for keyword in ['seller', 'user', 'rating', 'review', 'owner'])):

                # Enhanced user patterns with more flexible matching
                user_patterns = [
                    r'"(?:user|seller|owner)"\s*:\s*\{[^}]*"(?:rating|averageRating)"\s*:\s*([0-9.]+)[^}]*"(?:reviewCount|totalReviews)"\s*:\s*(\d+)',
                    r'"(?:rating|averageRating)"\s*:\s*([0-9.]+)[^,}]*"(?:reviewCount|totalReviews)"\s*:\s*(\d+)',
                    r'"(?:averageRating|rating)"\s*:\s*([0-9.]+)[^,}]*"(?:totalReviews|reviews)"\s*:\s*(\d+)',
                    r'(?:seller|user)[^}]*rating["\s]*:["\s]*([0-9.]+)[^}]*reviews?["\s]*:["\s]*(\d+)',
                    r'rating["\s]*:["\s]*([0-9.]+)[^}]*(?:seller|user)[^}]*reviews?["\s]*:["\s]*(\d+)',
                ]

                for pattern in user_patterns:
                    match = re.search(pattern, script_content, re.IGNORECASE)
                    if match:
                        try:
                            rating_val = float(match.group(1))
                            review_val = int(match.group(2))
                            if 0 <= rating_val <= 5 and review_val >= 0:
                                avg_rating = rating_val
                                num_reviews = review_val
                                logger.debug(f"Found seller data in listing: rating={avg_rating}, reviews={num_reviews}")
                                break
                        except (ValueError, IndexError):
                            continue

                # Enhanced trusted badge patterns
                trusted_patterns = [
                    r'"(?:trustedSeller|trusted|isTrusted|verified|verifiedSeller)"\s*:\s*true',
                    r'"badge"\s*:\s*"trusted"',
                    r'"status"\s*:\s*"trusted"',
                    r'trusted["\s]*:["\s]*true',
                    r'verified["\s]*:["\s]*true',
                ]

                for pattern in trusted_patterns:
                    if re.search(pattern, script_content, re.IGNORECASE):
                        trusted_badge = True
                        logger.debug("Found trusted badge in listing")
                        break

        # If no data found in listing, try to get from profile
        if avg_rating == 0.0 and num_reviews == 0:
            logger.debug("No seller data in listing, trying profile fetch")
            try:
                async with session.get(profile_url, timeout=10) as response:
                    if response.status == 200:
                        profile_html = await response.text()
                        profile_soup = BeautifulSoup(profile_html, 'lxml')

                        # Try basic profile extraction
                        profile_data = await analyze_seller_profile(profile_url, session)
                        if profile_data:
                            avg_rating = profile_data.get('avg_rating', 0.0)
                            num_reviews = profile_data.get('num_reviews', 0)
                            trusted_badge = profile_data.get('trusted_badge', False)
                            logger.debug(f"Got data from profile: rating={avg_rating}, reviews={num_reviews}")
            except Exception as e:
                logger.warning(f"Failed to fetch profile data: {e}")

        # Get last update
        last_updated = datetime.now(UTC)
        if profile_url:
            profile_last_update = await _fetch_seller_last_update(profile_url, session)
            if profile_last_update:
                last_updated = profile_last_update

        # Return data if we found any meaningful seller information
        if avg_rating > 0 or num_reviews > 0 or trusted_badge or profile_url:
            seller_data = SellerData(
                num_reviews=num_reviews,
                avg_rating=avg_rating,
                trusted_badge=trusted_badge,
                last_updated=last_updated
            )
            logger.debug(f"Returning seller data: {seller_data}")
            return seller_data

        logger.debug("No meaningful seller data found")
        return None

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
            html = await response.text()
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
    
    Note: Due to Grailed's dynamic loading, profile pages may not contain
    seller metrics in the initial HTML. This function attempts to extract
    available data but may return minimal information. For better seller
    analysis, use data extracted from listing pages.
    
    Args:
        profile_url: Grailed seller profile URL to analyze
        session: aiohttp ClientSession for making HTTP requests
    
    Returns:
        Dictionary containing seller metrics:
        - num_reviews: Number of seller reviews (often 0 from profile pages)
        - avg_rating: Average seller rating (often 0.0 from profile pages)
        - trusted_badge: Whether seller has trusted badge (often False from profile pages)
        - last_updated: DateTime of last seller activity
        Returns None if profile analysis fails.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Enhanced headers to mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        async with session.get(profile_url, headers=headers) as response:
            response.raise_for_status()
            html = await response.text()
    except Exception as e:
        logger.error(f"Failed to fetch profile {profile_url}: {e}")
        return None
    
    soup = BeautifulSoup(html, 'lxml')
    
    avg_rating = 0.0
    num_reviews = 0
    trusted_badge = False
    
    # Enhanced search patterns for seller data
    
    # 1. Try to find data in any script tags with enhanced patterns
    for script in soup.find_all('script'):
        if not script.string:
            continue
            
        script_content = script.string
        
        # Skip very large scripts (category data, etc.)
        if len(script_content) > 100000:
            continue
            
        # Look for any JSON objects that might contain user data
        try:
            # Try to find JSON objects in the script
            json_patterns = [
                r'({[^{}]*"(?:rating|review|user|seller|profile)"[^{}]*})',
                r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                r'window\.__PRELOADED_STATE__\s*=\s*({.*?});',
                r'__APOLLO_STATE__\s*=\s*({.*?});',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, script_content, re.DOTALL)
                for match in matches:
                    try:
                        import json
                        data = json.loads(match)
                        
                        # Recursively search for seller data
                        def find_seller_data(obj, path=""):
                            nonlocal avg_rating, num_reviews, trusted_badge
                            
                            if isinstance(obj, dict):
                                for key, value in obj.items():
                                    # Look for rating values
                                    if 'rating' in key.lower() and isinstance(value, (int, float)):
                                        if 0 <= value <= 5:
                                            avg_rating = float(value)
                                            logger.debug(f"Found rating in JSON: {avg_rating}")
                                    
                                    # Look for review counts
                                    elif any(keyword in key.lower() for keyword in ['review', 'feedback']) and isinstance(value, int):
                                        if value >= 0:
                                            num_reviews = value
                                            logger.debug(f"Found review count in JSON: {num_reviews}")
                                    
                                    # Look for trusted status
                                    elif any(keyword in key.lower() for keyword in ['trusted', 'verified']) and value is True:
                                        trusted_badge = True
                                        logger.debug(f"Found trusted badge in JSON")
                                    
                                    # Recurse into nested objects
                                    elif isinstance(value, dict):
                                        find_seller_data(value, f"{path}.{key}")
                            
                            elif isinstance(obj, list):
                                for i, item in enumerate(obj[:10]):  # Limit recursion
                                    if isinstance(item, dict):
                                        find_seller_data(item, f"{path}[{i}]")
                        
                        find_seller_data(data)
                        
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
    
    # 2. Try to find data in HTML elements with enhanced selectors
    if avg_rating == 0.0 and num_reviews == 0:
        # Look for any numeric content that might be ratings or reviews
        all_text_elements = soup.find_all(string=re.compile(r'\d'))
        for element in all_text_elements:
            text = element.strip()
            
            # Look for rating patterns (e.g., "4.8", "4.8/5", "Rating: 4.8")
            rating_match = re.search(r'(?:rating|score)[:\s]*([0-5]\.[0-9])', text, re.IGNORECASE)
            if rating_match:
                try:
                    rating_val = float(rating_match.group(1))
                    if 0 <= rating_val <= 5:
                        avg_rating = rating_val
                        logger.debug(f"Found rating in text: {avg_rating}")
                except ValueError:
                    pass
            
            # Look for review count patterns
            review_match = re.search(r'(\d+)\s*(?:review|feedback|rating)s?', text, re.IGNORECASE)
            if review_match:
                try:
                    review_count = int(review_match.group(1))
                    if review_count >= 0:
                        num_reviews = review_count
                        logger.debug(f"Found review count in text: {num_reviews}")
                except ValueError:
                    pass
        
        # Look for trusted/verified indicators in text
        page_text = soup.get_text().lower()
        if any(keyword in page_text for keyword in ['trusted seller', 'verified seller', 'trusted badge']):
            trusted_badge = True
            logger.debug("Found trusted indicator in page text")
    
    # 3. Look for specific meta tags or data attributes
    meta_tags = soup.find_all('meta')
    for meta in meta_tags:
        content = meta.get('content', '').lower()
        if 'rating' in content:
            rating_match = re.search(r'([0-5]\.[0-9])', content)
            if rating_match:
                try:
                    rating_val = float(rating_match.group(1))
                    if 0 <= rating_val <= 5:
                        avg_rating = rating_val
                        logger.debug(f"Found rating in meta: {avg_rating}")
                except ValueError:
                    pass
    
    # Return results
    last_updated = datetime.now(UTC)
    
    if avg_rating > 0 or num_reviews > 0 or trusted_badge:
        logger.info(f"Successfully extracted seller data: rating={avg_rating}, reviews={num_reviews}, trusted={trusted_badge}")
    else:
        logger.warning(f"No seller data found in profile {profile_url}. This may be due to dynamic loading.")
    
    return {
        'num_reviews': num_reviews,
        'avg_rating': avg_rating,
        'trusted_badge': trusted_badge,
        'last_updated': last_updated
    }
