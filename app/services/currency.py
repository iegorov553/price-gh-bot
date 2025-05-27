"""Currency exchange rate service.

Handles fetching and caching of USD to RUB exchange rates from the Central
Bank of Russia API. Applies configured markup and provides fallback handling
for API failures. Includes in-memory caching to reduce API calls.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import xml.etree.ElementTree as ET

import aiohttp

from ..config import config
from ..models import CurrencyRate

logger = logging.getLogger(__name__)

# Simple in-memory cache for rates
_rate_cache = {}
_cache_ttl = timedelta(hours=1)


async def get_usd_to_rub_rate(session: aiohttp.ClientSession) -> Optional[CurrencyRate]:
    """Get USD to RUB exchange rate from Central Bank of Russia.
    
    Fetches current exchange rate from CBR XML API, applies configured markup,
    and caches result for 1 hour. Returns None if API is unavailable.
    
    Args:
        session: aiohttp session for making requests.
    
    Returns:
        CurrencyRate object with rate and metadata, None if failed.
    """
    cache_key = "USD_RUB"
    now = datetime.now()
    
    # Check cache first
    if cache_key in _rate_cache:
        cached_rate, cached_time = _rate_cache[cache_key]
        if now - cached_time < _cache_ttl:
            logger.debug("Using cached USD to RUB rate")
            return cached_rate
    
    try:
        logger.info("Fetching USD to RUB exchange rate from Central Bank of Russia...")
        
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        async with session.get(url, timeout=20) as response:
            response.raise_for_status()
            content = await response.read()
        
        logger.info(f"Got response from CBR, status: {response.status}")
        
        # Parse XML response
        root = ET.fromstring(content)
        logger.info(f"Successfully parsed CBR XML, date: {root.get('Date')}")
        
        # Find USD currency entry
        for valute in root.findall('Valute'):
            char_code = valute.find('CharCode')
            if char_code is not None and char_code.text == 'USD':
                value_elem = valute.find('Value')
                nominal_elem = valute.find('Nominal')
                
                if value_elem is not None and nominal_elem is not None:
                    # CBR uses comma as decimal separator
                    value_str = value_elem.text.replace(',', '.')
                    nominal_str = nominal_elem.text
                    
                    base_rate = Decimal(value_str) / Decimal(nominal_str)
                    logger.info(f"CBR USD rate: {base_rate} RUB per USD")
                    
                    # Apply markup
                    markup_multiplier = Decimal('1') + (Decimal(str(config.currency.markup_percentage)) / Decimal('100'))
                    final_rate = (base_rate * markup_multiplier).quantize(Decimal('0.01'), ROUND_HALF_UP)
                    
                    logger.info(f"Final USD to RUB rate: {base_rate} -> {final_rate} (with {config.currency.markup_percentage}% markup)")
                    
                    rate = CurrencyRate(
                        from_currency="USD",
                        to_currency="RUB",
                        rate=final_rate,
                        source="cbr",
                        fetched_at=now,
                        markup_percentage=config.currency.markup_percentage
                    )
                    
                    # Cache the result
                    _rate_cache[cache_key] = (rate, now)
                    
                    return rate
        
        raise ValueError("USD currency not found in CBR response")
        
    except Exception as e:
        error_msg = f"CBR API failed: {e}"
        logger.error(error_msg)
        return None


async def get_rate(from_currency: str, to_currency: str, session: aiohttp.ClientSession) -> Optional[CurrencyRate]:
    """Get exchange rate for specified currency pair.
    
    Currently only supports USD to RUB conversion. Other currency pairs
    will return None with a warning log.
    
    Args:
        from_currency: Source currency code (e.g., 'USD').
        to_currency: Target currency code (e.g., 'RUB').
        session: aiohttp session for making requests.
    
    Returns:
        CurrencyRate object with rate and metadata, None if currency pair
        not supported or conversion failed.
    """
    if from_currency == "USD" and to_currency == "RUB":
        return await get_usd_to_rub_rate(session)
    
    logger.warning(f"Currency pair {from_currency}/{to_currency} not supported")
    return None


def clear_cache():
    """Clear the in-memory currency rate cache.
    
    Removes all cached exchange rates, forcing fresh API calls on next
    rate requests. Useful for testing or when manual cache invalidation
    is needed.
    """
    global _rate_cache
    _rate_cache.clear()
    logger.info("Currency rate cache cleared")