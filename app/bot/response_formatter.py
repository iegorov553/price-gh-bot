"""Response formatting for bot messages and user interactions.

Handles formatting of price calculations, seller analysis, error messages,
and other user-facing content with proper localization and structure.
"""

import logging
from typing import Dict, Any, List, Optional

from ..models import PriceCalculation, ReliabilityScore
from ..services import currency, shipping
from .messages import (
    ERROR_PRICE_NOT_FOUND,
    ERROR_SELLER_ANALYSIS,
    ERROR_SELLER_DATA_NOT_FOUND,
    GRAILED_LISTING_ISSUE,
    GRAILED_SITE_DOWN,
    GRAILED_SITE_SLOW,
    OFFER_ONLY_MESSAGE,
)
from .utils import (
    calculate_final_price_from_item,
    format_price_response,
    format_seller_profile_response,
)

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """Formats bot responses for different types of content.
    
    Responsibilities:
    - Format price calculation responses
    - Format seller analysis responses  
    - Format error messages with context
    - Handle offer-only vs buyable items
    - Create loading messages and status updates
    """
    
    def __init__(self):
        """Initialize response formatter."""
        pass
    
    async def format_item_response(
        self, 
        scraping_result: Dict[str, Any]
    ) -> str:
        """Format response for item listing analysis.
        
        Args:
            scraping_result: Result from scraping orchestrator.
            
        Returns:
            Formatted message string for user.
        """
        if not scraping_result['success']:
            return self._format_error_response(scraping_result)
            
        item_data = scraping_result['item_data']
        seller_data = scraping_result.get('seller_data')
        
        if not item_data:
            return ERROR_PRICE_NOT_FOUND
            
        # Check if item is buyable
        if not item_data.is_buyable:
            return self._format_offer_only_response(item_data)
            
        # Calculate final price
        try:
            price_calculation = await calculate_final_price_from_item(item_data)
            
            # Get USD to RUB exchange rate
            from ..services import currency
            exchange_rate = None
            try:
                # Use a temporary session for currency
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    exchange_rate = await currency.get_usd_to_rub_rate(session)
            except Exception as e:
                logger.warning(f"Failed to get exchange rate: {e}")
            
            # Calculate seller reliability for Grailed
            reliability_score = None
            if seller_data and scraping_result['platform'] == 'grailed':
                from ..services import reliability
                reliability_score = reliability.calculate_reliability_score(seller_data)
            
            # Format main price response
            response = format_price_response(
                calculation=price_calculation,
                exchange_rate=exchange_rate,
                reliability=reliability_score,
                is_grailed=(scraping_result['platform'] == 'grailed'),
                item_title=item_data.title,
                item_url=scraping_result.get('url'),
                use_markdown=False
            )
                
            return response
            
        except Exception as e:
            logger.error(f"Failed to calculate price: {e}")
            return ERROR_PRICE_NOT_FOUND
    
    def format_seller_profile_response(
        self,
        scraping_result: Dict[str, Any]
    ) -> str:
        """Format response for seller profile analysis.
        
        Args:
            scraping_result: Result from scraping orchestrator.
            
        Returns:
            Formatted seller analysis message.
        """
        if not scraping_result['success']:
            return self._format_seller_error_response(scraping_result)
            
        seller_data = scraping_result['seller_data']
        reliability_score = scraping_result['reliability_score']
        
        if not seller_data or not reliability_score:
            return ERROR_SELLER_DATA_NOT_FOUND
            
        return format_seller_profile_response(seller_data, reliability_score)
    
    async def format_multiple_urls_response(
        self,
        results: List[Dict[str, Any]]
    ) -> List[str]:
        """Format responses for multiple URL processing.
        
        Args:
            results: List of scraping results.
            
        Returns:
            List of formatted response messages.
        """
        responses = []
        
        for result in results:
            platform = result['platform']
            
            if platform == 'profile':
                response = self.format_seller_profile_response(result)
            else:
                response = await self.format_item_response(result)
                
            responses.append(response)
            
        return responses
    
    def _format_error_response(self, result: Dict[str, Any]) -> str:
        """Format error response based on platform and error type.
        
        Args:
            result: Scraping result with error.
            
        Returns:
            Formatted error message.
        """
        platform = result['platform']
        error = result.get('error', 'Unknown error')
        
        # Grailed-specific error handling
        if platform == 'grailed':
            if 'timeout' in error.lower() or 'slow' in error.lower():
                return GRAILED_SITE_SLOW
            elif 'connection' in error.lower() or 'unavailable' in error.lower():
                return GRAILED_SITE_DOWN
            elif 'listing' in error.lower():
                return GRAILED_LISTING_ISSUE
                
        # Generic error message
        logger.error(f"Scraping error for {platform}: {error}")
        return ERROR_PRICE_NOT_FOUND
    
    def _format_seller_error_response(self, result: Dict[str, Any]) -> str:
        """Format seller analysis error response.
        
        Args:
            result: Scraping result with error.
            
        Returns:
            Formatted error message.
        """
        error = result.get('error', 'Unknown error')
        
        if 'headless' in error.lower() or 'browser' in error.lower():
            return ("❌ Анализ продавца временно недоступен\n"
                   "Попробуйте позже или используйте ссылку на товар")
        
        logger.error(f"Seller analysis error: {error}")
        return ERROR_SELLER_ANALYSIS
    
    def _format_offer_only_response(self, item_data) -> str:
        """Format response for offer-only items.
        
        Args:
            item_data: Item data object.
            
        Returns:
            Formatted offer-only message.
        """
        # Show price for reference even if not buyable
        price_text = f"${item_data.price:.2f}" if item_data.price else "Цена не указана"
        
        return OFFER_ONLY_MESSAGE.format(
            title=item_data.title or "Товар",
            price=price_text
        )
    
    def _format_seller_section(self, seller_data) -> str:
        """Format seller reliability section for item responses.
        
        Args:
            seller_data: Seller data object.
            
        Returns:
            Formatted seller section.
        """
        try:
            from ..services import reliability
            
            reliability_score = reliability.calculate_reliability_score(seller_data)
            
            # Compact seller info for item responses
            emoji = {
                'Diamond': '💎',
                'Gold': '🥇', 
                'Silver': '🥈',
                'Bronze': '🥉',
                'Ghost': '👻',
                'No Data': 'ℹ️'
            }.get(reliability_score.category, 'ℹ️')
            
            return (f"**Продавец:** {emoji} {reliability_score.category} "
                   f"({reliability_score.total_score}/100)")
            
        except Exception as e:
            logger.error(f"Failed to format seller section: {e}")
            return ""
    
    def format_loading_message(self, urls: List[str]) -> str:
        """Format loading message for URL processing.
        
        Args:
            urls: List of URLs being processed.
            
        Returns:
            Loading message string.
        """
        if len(urls) == 1:
            return "⏳ Загружаем данные и производим расчёт..."
        else:
            return f"⏳ Обрабатываем {len(urls)} ссылок..."
    
    def format_analytics_response(
        self,
        stats: Dict[str, Any],
        title: str
    ) -> str:
        """Format analytics statistics response.
        
        Args:
            stats: Statistics dictionary.
            title: Response title.
            
        Returns:
            Formatted analytics message.
        """
        if not stats:
            return "❌ Не удалось получить статистику"
            
        message = f"📊 **{title}**\n\n"
        message += f"🔍 Всего поисков: {stats['total_searches']}\n"
        message += f"✅ Успешных: {stats['successful_searches']}\n"
        message += f"📈 Процент успеха: {stats['success_rate']:.1%}\n"
        message += f"⏱️ Среднее время: {stats['avg_processing_time_ms']:.0f}мс\n\n"
        
        if 'platforms' in stats and stats['platforms']:
            message += "**Платформы:**\n"
            for platform, count in stats['platforms'].items():
                message += f"• {platform}: {count}\n"
        else:
            message += "**Платформы:** нет данных\n"
                
        return message


# Global response formatter instance  
response_formatter = ResponseFormatter()