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
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from ..models import ItemData, SellerData


PRICE_RE = re.compile(r"^\d[\d,.]*$")


def _clean_price(raw: str) -> Optional[Decimal]:
    """Clean and parse price string."""
    raw = raw.strip()
    if not PRICE_RE.match(raw):
        return None
    try:
        return Decimal(raw.replace(',', ''))
    except Exception:
        return None


def _parse_json_ld(soup: BeautifulSoup) -> Optional[Decimal]:
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


def _scrape_shipping_grailed(soup: BeautifulSoup) -> Optional[Decimal]:
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


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    """Extract item title."""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"]
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


def _extract_price_and_buyability(url: str, soup: BeautifulSoup) -> Tuple[Optional[Decimal], bool]:
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


def _extract_seller_profile_url(soup: BeautifulSoup) -> Optional[str]:
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


async def _fetch_seller_last_update(profile_url: str, session: aiohttp.ClientSession) -> Optional[datetime]:
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
                                date_obj = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                            elif 'T' in date_str:
                                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            else:
                                date_obj = datetime.fromisoformat(date_str)
                                if date_obj.tzinfo is None:
                                    date_obj = date_obj.replace(tzinfo=timezone.utc)
                            
                            if latest_date is None or date_obj > latest_date:
                                latest_date = date_obj
                        except Exception:
                            continue
        
        return latest_date
    except Exception:
        return None


async def _extract_seller_data(soup: BeautifulSoup, session: aiohttp.ClientSession) -> Optional[SellerData]:
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
        
        # Look for seller data in listing JSON
        for script in soup.find_all('script'):
            if not script.string:
                continue
                
            script_content = script.string
            if any(keyword in script_content.lower() for keyword in ['seller', 'user', 'rating', 'review', 'owner']):
                
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
        last_updated = datetime.now(timezone.utc)
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


async def get_item_data(url: str, session: aiohttp.ClientSession) -> Tuple[ItemData, Optional[SellerData]]:
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


async def analyze_seller_profile(profile_url: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
    """Analyze Grailed seller profile for reliability metrics.
    
    Performs comprehensive analysis of a Grailed seller's profile to extract
    reliability indicators including average rating, review count, trusted badge
    status, and last activity date. Uses multiple parsing strategies with
    JSON and HTML fallbacks for robust data extraction.
    
    Args:
        profile_url: Grailed seller profile URL to analyze
        session: aiohttp ClientSession for making HTTP requests
    
    Returns:
        Dictionary containing seller metrics:
        - num_reviews: Number of seller reviews
        - avg_rating: Average seller rating (0.0-5.0)
        - trusted_badge: Whether seller has trusted badge
        - last_updated: DateTime of last seller activity
        Returns None if profile analysis fails.
    """
    try:
        async with session.get(profile_url) as response:
            response.raise_for_status()
            html = await response.text()
    except Exception:
        return None
    
    soup = BeautifulSoup(html, 'lxml')
    
    avg_rating = 0.0
    num_reviews = 0
    trusted_badge = False
    
    # Extract seller data from profile - improved patterns
    import logging
    logger = logging.getLogger(__name__)
    
    for script in soup.find_all('script'):
        if not script.string:
            continue
            
        script_content = script.string
        if any(keyword in script_content.lower() for keyword in ['rating', 'review', 'user', 'seller', 'profile']):
            
            # Comprehensive rating patterns
            rating_patterns = [
                r'"(?:rating|averageRating|avgRating|sellerRating)"\s*:\s*([0-9.]+)',
                r'"rating"\s*:\s*\{\s*"value"\s*:\s*([0-9.]+)',
                r'rating["\s]*:["\s]*([0-9.]+)',
                r'"stars"\s*:\s*([0-9.]+)',
                r'"score"\s*:\s*([0-9.]+)',
            ]
            
            # Comprehensive review count patterns  
            review_patterns = [
                r'"(?:reviewCount|totalReviews|numReviews|reviews)"\s*:\s*(\d+)',
                r'"count"\s*:\s*(\d+)[^}]*"(?:review|rating)"',
                r'reviews?["\s]*:["\s]*(\d+)',
                r'"feedbackCount"\s*:\s*(\d+)',
                r'"ratingsCount"\s*:\s*(\d+)',
            ]
            
            # Try to find rating
            for pattern in rating_patterns:
                rating_match = re.search(pattern, script_content, re.IGNORECASE)
                if rating_match:
                    try:
                        rating_value = float(rating_match.group(1))
                        if 0 <= rating_value <= 5:  # Valid rating range
                            avg_rating = rating_value
                            logger.debug(f"Found rating: {avg_rating}")
                            break
                    except (ValueError, IndexError):
                        continue
            
            # Try to find review count
            for pattern in review_patterns:
                review_match = re.search(pattern, script_content, re.IGNORECASE)
                if review_match:
                    try:
                        review_count = int(review_match.group(1))
                        if review_count >= 0:  # Valid count
                            num_reviews = review_count
                            logger.debug(f"Found review count: {num_reviews}")
                            break
                    except (ValueError, IndexError):
                        continue
            
            # Enhanced trusted badge patterns
            trusted_patterns = [
                r'"(?:trustedSeller|trusted|isTrusted|verified|verifiedSeller)"\s*:\s*true',
                r'"badge"\s*:\s*"trusted"',
                r'"status"\s*:\s*"trusted"',
                r'"tier"\s*:\s*"trusted"',
                r'trusted["\s]*:["\s]*true',
                r'verified["\s]*:["\s]*true',
            ]
            
            for pattern in trusted_patterns:
                if re.search(pattern, script_content, re.IGNORECASE):
                    trusted_badge = True
                    logger.debug("Found trusted badge")
                    break
    
    # Also try HTML parsing as fallback
    if avg_rating == 0.0 and num_reviews == 0:
        logger.debug("Trying HTML fallback for seller data")
        
        # Look for rating in text content
        rating_elements = soup.find_all(string=re.compile(r'[0-9.]+\s*(?:star|rating|\/5)'))
        for element in rating_elements:
            rating_match = re.search(r'([0-9.]+)', element)
            if rating_match:
                try:
                    rating_value = float(rating_match.group(1))
                    if 0 <= rating_value <= 5:
                        avg_rating = rating_value
                        break
                except ValueError:
                    continue
        
        # Look for review count in text
        review_elements = soup.find_all(string=re.compile(r'\d+\s*(?:review|rating|feedback)'))
        for element in review_elements:
            review_match = re.search(r'(\d+)', element)
            if review_match:
                try:
                    review_count = int(review_match.group(1))
                    if review_count >= 0:
                        num_reviews = review_count
                        break
                except ValueError:
                    continue
    
    # Get last update
    last_updated = await _fetch_seller_last_update(profile_url, session)
    if not last_updated:
        last_updated = datetime.now(timezone.utc)
    
    return {
        'num_reviews': num_reviews,
        'avg_rating': avg_rating,
        'trusted_badge': trusted_badge,
        'last_updated': last_updated
    }