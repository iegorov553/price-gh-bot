"""URL processing and validation for marketplace links.

Handles URL detection, validation, and categorization for supported
marketplaces. Provides security filtering and platform detection.
"""

import logging
import re
from typing import List
from urllib.parse import urlparse

from ..scrapers import scraper_registry
from .utils import validate_marketplace_url

logger = logging.getLogger(__name__)


class URLProcessor:
    """Handles URL detection, validation and categorization.
    
    Responsible for:
    - Extracting URLs from user messages
    - Validating URLs against security whitelist
    - Categorizing URLs by platform (eBay, Grailed, etc.)
    - Filtering out malicious or unsupported URLs
    """
    
    def __init__(self):
        """Initialize URL processor with security settings."""
        self.url_pattern = re.compile(r"(https?://[\w\.-]+(?:/[^\s]*)?)")
        
    def extract_urls(self, text: str) -> List[str]:
        """Extract all URLs from text message.
        
        Args:
            text: User message text.
            
        Returns:
            List of detected URLs.
        """
        if not text:
            return []
            
        urls = self.url_pattern.findall(text)
        logger.debug(f"Extracted {len(urls)} URLs from text")
        return urls
    
    def validate_urls(self, urls: List[str]) -> List[str]:
        """Filter URLs to only include supported marketplaces.
        
        Args:
            urls: List of URLs to validate.
            
        Returns:
            List of valid marketplace URLs.
        """
        valid_urls = []
        invalid_urls = []
        
        for url in urls:
            if validate_marketplace_url(url):
                valid_urls.append(url)
            else:
                invalid_urls.append(url)
                
        if invalid_urls:
            logger.warning(f"Filtered out invalid URLs: {invalid_urls}")
            
        logger.info(f"Validated {len(valid_urls)}/{len(urls)} URLs")
        return valid_urls
    
    def categorize_urls(self, urls: List[str]) -> dict:
        """Categorize URLs by platform and type.
        
        Args:
            urls: List of valid URLs.
            
        Returns:
            Dictionary with categorized URLs:
            {
                'seller_profiles': [urls],
                'item_listings': [urls],
                'by_platform': {'ebay': [urls], 'grailed': [urls]}
            }
        """
        result = {
            'seller_profiles': [],
            'item_listings': [],
            'by_platform': {'ebay': [], 'grailed': [], 'unknown': []}
        }
        
        for url in urls:
            # Find scraper for URL
            scraper = scraper_registry.get_scraper_for_url(url)
            
            if not scraper:
                result['by_platform']['unknown'].append(url)
                continue
            
            platform = scraper.get_platform_name()
            
            # Check if it's a seller profile or item listing
            if scraper.is_seller_profile(url):
                result['seller_profiles'].append(url)
                result['by_platform'][platform].append(url)
            else:
                result['item_listings'].append(url)
                result['by_platform'][platform].append(url)
                
        return result
    
    def process_message(self, text: str, user_id: int | None = None) -> dict:
        """Complete URL processing pipeline for user message.
        
        Args:
            text: User message text.
            user_id: User ID for security logging.
            
        Returns:
            Dictionary with processed URLs and metadata:
            {
                'valid_urls': [urls],
                'categorized': {...},
                'has_suspicious': bool
            }
        """
        # Extract all URLs
        raw_urls = self.extract_urls(text)
        
        if not raw_urls:
            return {
                'valid_urls': [],
                'categorized': {},
                'has_suspicious': False
            }
        
        # Validate URLs
        valid_urls = self.validate_urls(raw_urls)
        
        # Log suspicious activity
        has_suspicious = len(valid_urls) < len(raw_urls)
        if has_suspicious and user_id:
            suspicious_urls = [url for url in raw_urls if url not in valid_urls]
            logger.warning(
                f"User {user_id} sent suspicious URLs: {suspicious_urls}"
            )
        
        # Categorize valid URLs
        categorized = self.categorize_urls(valid_urls) if valid_urls else {}
        
        return {
            'valid_urls': valid_urls,
            'categorized': categorized,
            'has_suspicious': has_suspicious
        }


# Global URL processor instance
url_processor = URLProcessor()