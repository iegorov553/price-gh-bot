"""Scraping orchestration and coordination for marketplace data extraction.

Coordinates scraping operations across different platforms, handles
concurrent processing, error recovery, and data aggregation.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

import aiohttp

from ..models import SearchAnalytics, SellerData
from ..scrapers import ebay, grailed
from ..services import currency, reliability, shipping
from ..services.analytics import analytics_service
from .utils import create_session, detect_platform

logger = logging.getLogger(__name__)


class ScrapingOrchestrator:
    """Orchestrates scraping operations across multiple platforms.
    
    Responsibilities:
    - Coordinate scraping across eBay/Grailed platforms
    - Handle concurrent URL processing
    - Manage error recovery and fallbacks
    - Aggregate and normalize data from different sources
    - Track analytics for all scraping operations
    """
    
    def __init__(self):
        """Initialize scraping orchestrator."""
        self.max_concurrent_urls = 5
        
    async def scrape_item_listing(
        self, 
        url: str, 
        session: aiohttp.ClientSession
    ) -> Dict[str, Any]:
        """Scrape individual item listing from marketplace.
        
        Args:
            url: Item listing URL.
            session: HTTP session for requests.
            
        Returns:
            Dictionary with item data and metadata:
            {
                'success': bool,
                'platform': str,
                'item_data': ItemData | None,
                'seller_data': SellerData | None,
                'error': str | None,
                'processing_time_ms': int
            }
        """
        start_time = datetime.now()
        platform = detect_platform(url)
        
        result = {
            'success': False,
            'platform': platform,
            'item_data': None,
            'seller_data': None,
            'error': None,
            'processing_time_ms': 0,
            'url': url
        }
        
        try:
            logger.info(f"Scraping {platform} item: {url}")
            
            if platform == 'ebay':
                item_data = await ebay.get_ebay_item_data(url, session)
                
            elif platform == 'grailed':
                item_data = await grailed.get_grailed_item_data(url, session)
                
                # Try to get seller data for Grailed items
                try:
                    seller_profile_url = grailed.extract_seller_profile_url(item_data)
                    if seller_profile_url:
                        seller_data = await grailed.get_grailed_seller_data(
                            seller_profile_url, session
                        )
                        result['seller_data'] = seller_data
                except Exception as e:
                    logger.warning(f"Failed to get seller data for {url}: {e}")
                    
            else:
                raise ValueError(f"Unsupported platform: {platform}")
                
            if item_data:
                result['success'] = True
                result['item_data'] = item_data
                logger.info(f"Successfully scraped {platform} item: {item_data.title}")
            else:
                result['error'] = f"No data extracted from {platform}"
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Failed to scrape {url}: {e}")
            
        finally:
            end_time = datetime.now()
            result['processing_time_ms'] = int(
                (end_time - start_time).total_seconds() * 1000
            )
            
        return result
    
    async def scrape_seller_profile(
        self,
        url: str,
        session: aiohttp.ClientSession
    ) -> Dict[str, Any]:
        """Scrape seller profile data.
        
        Args:
            url: Seller profile URL.
            session: HTTP session for requests.
            
        Returns:
            Dictionary with seller analysis results.
        """
        start_time = datetime.now()
        
        result = {
            'success': False,
            'seller_data': None,
            'reliability_score': None,
            'error': None,
            'processing_time_ms': 0,
            'url': url
        }
        
        try:
            logger.info(f"Analyzing seller profile: {url}")
            
            # Extract seller data
            seller_data = await grailed.get_grailed_seller_data(url, session)
            
            if seller_data:
                result['success'] = True
                result['seller_data'] = seller_data
                
                # Calculate reliability score
                reliability_score = reliability.calculate_reliability_score(seller_data)
                result['reliability_score'] = reliability_score
                
                logger.info(f"Seller analysis complete: {reliability_score.category}")
            else:
                result['error'] = "No seller data found"
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Failed to analyze seller {url}: {e}")
            
        finally:
            end_time = datetime.now()
            result['processing_time_ms'] = int(
                (end_time - start_time).total_seconds() * 1000
            )
            
        return result
    
    async def process_urls_concurrent(
        self,
        urls: List[str],
        user_id: int,
        username: str | None = None
    ) -> List[Dict[str, Any]]:
        """Process multiple URLs concurrently.
        
        Args:
            urls: List of URLs to process.
            user_id: User ID for analytics.
            username: Username for analytics.
            
        Returns:
            List of processing results for each URL.
        """
        if not urls:
            return []
            
        async with create_session() as session:
            # Create semaphore to limit concurrent requests
            semaphore = asyncio.Semaphore(self.max_concurrent_urls)
            
            async def process_single_url(url: str) -> Dict[str, Any]:
                async with semaphore:
                    platform = detect_platform(url)
                    
                    if platform == 'profile':
                        return await self.scrape_seller_profile(url, session)
                    else:
                        return await self.scrape_item_listing(url, session)
            
            # Process all URLs concurrently
            results = await asyncio.gather(
                *[process_single_url(url) for url in urls],
                return_exceptions=True
            )
            
            # Handle exceptions and log analytics
            processed_results = []
            for i, result in enumerate(results):
                url = urls[i]
                
                if isinstance(result, Exception):
                    result = {
                        'success': False,
                        'error': str(result),
                        'url': url,
                        'platform': detect_platform(url),
                        'processing_time_ms': 0
                    }
                
                processed_results.append(result)
                
                # Log to analytics
                await self._log_analytics(result, user_id, username)
                
            return processed_results
    
    async def _log_analytics(
        self,
        result: Dict[str, Any],
        user_id: int,
        username: str | None = None
    ) -> None:
        """Log scraping result to analytics.
        
        Args:
            result: Scraping result dictionary.
            user_id: User ID.
            username: Username.
        """
        try:
            analytics_data = SearchAnalytics(
                user_id=user_id,
                username=username,
                timestamp=datetime.now(),
                url=result['url'],
                platform=result['platform'],
                success=result['success'],
                processing_time_ms=result['processing_time_ms'],
                error_type=result.get('error'),
                
                # Item data if available
                item_title=getattr(result.get('item_data'), 'title', None),
                item_price_usd=getattr(result.get('item_data'), 'price', None),
                shipping_cost_usd=getattr(result.get('item_data'), 'shipping_cost', None),
                
                # Seller data if available
                seller_rating=getattr(result.get('seller_data'), 'rating', None),
                seller_reviews=getattr(result.get('seller_data'), 'total_reviews', None),
                seller_trusted=getattr(result.get('seller_data'), 'trusted_badge', None),
                
                # Final price if calculated
                total_price_rub=None  # Will be filled by response formatter
            )
            
            analytics_service.log_search(analytics_data)
            
        except Exception as e:
            logger.error(f"Failed to log analytics: {e}")


# Global orchestrator instance
scraping_orchestrator = ScrapingOrchestrator()