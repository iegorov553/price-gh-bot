"""
Оптимизированный headless browser scraper с browser pool.

Этот модуль заменяет оригинальный headless.py с улучшенной производительностью:
- Использует browser pool для переиспользования браузеров
- Сокращенные задержки с сохранением человекоподобного поведения  
- Параллельное извлечение данных
- Умное извлечение активности продавца
"""

import asyncio
import logging
import re
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

try:
    from playwright.async_api import Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    Page = None
    PLAYWRIGHT_AVAILABLE = False

from ..models import SellerData
from ..services.browser_pool import get_browser_pool

logger = logging.getLogger(__name__)


async def extract_seller_data_optimized(url: str) -> Optional[SellerData]:
    """
    Оптимизированное извлечение данных продавца с browser pool.
    
    Ожидаемое ускорение: 8-10с → 3-4с (60-70%)
    
    Args:
        url: URL Grailed профиля или листинга
        
    Returns:
        SellerData с извлеченными метриками или None
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright недоступен, возвращаем None")
        return None
    
    pool = await get_browser_pool()
    page = await pool.acquire_page()
    
    try:
        start_time = datetime.now()
        
        # Быстрая навигация с сокращенными задержками
        await page.goto(url, wait_until='domcontentloaded', timeout=10000)
        await asyncio.sleep(0.2)  # Было 0.8-1.2с
        
        # Параллельное извлечение всех данных
        rating_task = asyncio.create_task(extract_rating_fast(page))
        reviews_task = asyncio.create_task(extract_reviews_fast(page))
        badge_task = asyncio.create_task(extract_trusted_badge_fast(page))
        activity_task = asyncio.create_task(extract_activity_smart(page))
        
        # Ждем завершения всех задач
        rating, reviews, badge, activity = await asyncio.gather(
            rating_task, reviews_task, badge_task, activity_task,
            return_exceptions=True
        )
        
        # Обрабатываем исключения
        rating = rating if not isinstance(rating, Exception) else 0.0
        reviews = reviews if not isinstance(reviews, Exception) else 0
        badge = badge if not isinstance(badge, Exception) else False
        activity = activity if not isinstance(activity, Exception) else None
        
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Headless extraction завершен за {execution_time:.2f}с: rating={rating}, reviews={reviews}, badge={badge}")
        
        return SellerData(
            avg_rating=rating,
            num_reviews=reviews,
            trusted_badge=badge,
            last_activity=activity
        )
        
    except Exception as e:
        logger.error(f"Ошибка оптимизированного извлечения для {url}: {e}")
        return None
    finally:
        await pool.release_page(page)


async def extract_rating_fast(page: Page) -> float:
    """Быстрое извлечение рейтинга продавца."""
    selectors = [
        '[data-testid*="rating"]',
        '.seller-rating', 
        '.rating',
        'text=/[0-5]\\.[0-9]/',
        '[aria-label*="rating"]'
    ]
    
    for selector in selectors[:3]:  # Проверяем только первые 3 для скорости
        try:
            elements = await page.query_selector_all(selector)
            for element in elements:
                text = await element.text_content()
                if text:
                    rating_match = re.search(r'([0-5]\.[0-9])', text)
                    if rating_match:
                        rating = float(rating_match.group(1))
                        if 0 <= rating <= 5:
                            return rating
        except Exception:
            continue
    
    return 0.0


async def extract_reviews_fast(page: Page) -> int:
    """Быстрое извлечение количества отзывов."""
    selectors = [
        '[data-testid*="review"]',
        '.review-count',
        '.feedback-count',
        'text=/\\d+ review/i',
        'text=/\\d+ feedback/i'
    ]
    
    for selector in selectors[:3]:  # Проверяем только первые 3
        try:
            elements = await page.query_selector_all(selector)
            for element in elements:
                text = await element.text_content()
                if text:
                    review_match = re.search(r'(\d+)', text)
                    if review_match:
                        count = int(review_match.group(1))
                        if count > 0:
                            return count
        except Exception:
            continue
    
    return 0


async def extract_trusted_badge_fast(page: Page) -> bool:
    """Быстрое определение trusted badge."""
    badge_selectors = [
        '[data-testid*="trusted"]',
        '.trusted-badge',
        '.verified-seller',
        'text=/trusted/i',
        'text=/verified/i'
    ]
    
    try:
        # Проверяем все селекторы параллельно
        tasks = []
        for selector in badge_selectors:
            tasks.append(page.query_selector(selector))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Если хотя бы один селектор найден - badge есть
        for result in results:
            if result and not isinstance(result, Exception):
                return True
                
    except Exception:
        pass
    
    return False


async def extract_activity_smart(page: Page) -> Optional[datetime]:
    """
    Умное извлечение активности продавца с одним скроллом.
    
    Заменяет 4 операции скроллинга одной эффективной.
    """
    try:
        # Один эффективный скролл для загрузки контента
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight/3)')
        await page.wait_for_timeout(300)  # Было 4 операции по 400-1200мс
        
        # Паттерны времени активности
        time_patterns = [
            r'(\d+)\s+days?\s+ago',
            r'(\d+)\s+weeks?\s+ago', 
            r'(\d+)\s+months?\s+ago',
            r'(\d+)\s+hours?\s+ago',
            r'Updated\s+(\d+)\s+days?\s+ago',
            r'Active\s+(\d+)\s+days?\s+ago'
        ]
        
        # Получаем весь текст страницы одним запросом
        page_text = await page.text_content('body')
        
        if page_text:
            for pattern in time_patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                if matches:
                    try:
                        value = int(matches[0])
                        
                        # Определяем единицу времени
                        if 'day' in pattern:
                            return datetime.now() - timedelta(days=value)
                        elif 'week' in pattern:
                            return datetime.now() - timedelta(weeks=value)
                        elif 'month' in pattern:
                            return datetime.now() - timedelta(days=value * 30)
                        elif 'hour' in pattern:
                            return datetime.now() - timedelta(hours=value)
                            
                    except (ValueError, IndexError):
                        continue
        
        # Fallback: ищем конкретные элементы активности
        activity_selectors = [
            '.listing-time',
            '.last-seen',
            '.activity-time',
            '[data-testid*="time"]'
        ]
        
        for selector in activity_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    if text:
                        for pattern in time_patterns:
                            match = re.search(pattern, text, re.IGNORECASE)
                            if match:
                                value = int(match.group(1))
                                if 'day' in pattern:
                                    return datetime.now() - timedelta(days=value)
                                elif 'week' in pattern:
                                    return datetime.now() - timedelta(weeks=value)
                                elif 'month' in pattern:
                                    return datetime.now() - timedelta(days=value * 30)
            except Exception:
                continue
                
    except Exception as e:
        logger.debug(f"Не удалось извлечь активность: {e}")
    
    return None


async def get_grailed_seller_data_optimized(url: str) -> Dict[str, Any]:
    """
    Главная функция для получения данных продавца Grailed (оптимизированная).
    
    Args:
        url: URL профиля или листинга Grailed
        
    Returns:
        Словарь с данными продавца
    """
    seller_data = await extract_seller_data_optimized(url)
    
    if seller_data:
        return {
            'rating': seller_data.avg_rating,
            'reviews': seller_data.num_reviews,
            'trusted_badge': seller_data.trusted_badge,
            'last_activity': seller_data.last_activity.isoformat() if seller_data.last_activity else None
        }
    else:
        return {
            'rating': None,
            'reviews': None,
            'trusted_badge': False,
            'last_activity': None
        }
        

# Сохраняем совместимость со старым API
async def extract_seller_data_headless(url: str, headless_browser=None) -> Optional[SellerData]:
    """Обратная совместимость со старым API."""
    return await extract_seller_data_optimized(url)