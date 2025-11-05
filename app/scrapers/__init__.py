"""Web scrapers package.

Contains marketplace-specific web scraping implementations for extracting
item data, pricing information, and seller profiles. Handles different
site structures and provides unified interfaces for eBay and Grailed.

Modern Architecture:
- ScraperProtocol: Unified interface for all marketplace scrapers
- ScraperRegistry: Centralized management and URL routing
- EbayScraper: eBay implementation with item data extraction
- GrailedScraper: Grailed implementation with item and seller analysis

Legacy modules (deprecated, use new scrapers instead):
- ebay: Direct eBay scraping functions
- grailed: Direct Grailed scraping functions  
- headless: Headless browser utilities
"""

# Import legacy modules for backward compatibility
from . import ebay, ebay_scraper, grailed, headless

# Import new unified scraper architecture
from .base import ScraperProtocol, BaseScraper, scraper_registry
from .ebay_scraper import ebay_scraper
from .grailed_scraper import grailed_scraper

# Auto-register all available scrapers
scraper_registry.register(ebay_scraper)
scraper_registry.register(grailed_scraper)

# Export main interfaces
__all__ = [
    # New unified architecture (recommended)
    'ScraperProtocol',
    'BaseScraper', 
    'scraper_registry',
    'ebay_scraper',
    'grailed_scraper',
    
    # Legacy modules (backward compatibility)
    'ebay',
    'grailed', 
    'headless'
]
