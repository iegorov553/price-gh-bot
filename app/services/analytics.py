"""Analytics service for tracking user search behavior and bot usage patterns.

Provides SQLite-based storage and retrieval of search analytics data including
user interactions, URL processing results, pricing calculations, and performance
metrics for business intelligence and optimization purposes.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from ..models import SearchAnalytics

logger = logging.getLogger(__name__)


class AnalyticsService:
    """SQLite-based analytics service for tracking user search behavior.
    
    Manages persistent storage of search queries, results, and performance metrics
    with comprehensive querying capabilities for business intelligence.
    
    Attributes:
        db_path: Path to SQLite database file.
    """
    
    def __init__(self, db_path: str | None = None):
        """Initialize analytics service with database connection.
        
        Args:
            db_path: Path to SQLite database file. Uses config default if None.
        """
        if db_path is None:
            # Use default path to avoid circular import
            import os
            self.db_path = os.getenv("ANALYTICS_DB_PATH", "data/analytics.db")
        else:
            self.db_path = db_path
        
        # Create data directory if it doesn't exist
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self._init_database()
        logger.info(f"Analytics service initialized with database: {db_path}")
    
    def _init_database(self) -> None:
        """Create analytics table if it doesn't exist.
        
        Creates the main search_analytics table with comprehensive schema
        for storing all search-related data and metadata.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    platform TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    item_price DECIMAL,
                    shipping_us DECIMAL,
                    item_title TEXT,
                    error_message TEXT,
                    processing_time_ms INTEGER,
                    seller_score INTEGER,
                    seller_category TEXT,
                    final_price_usd DECIMAL,
                    commission DECIMAL,
                    is_buyable BOOLEAN
                )
            """)
            
            # Create indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_id 
                ON search_analytics(user_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_platform 
                ON search_analytics(platform)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON search_analytics(timestamp)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_success 
                ON search_analytics(success)
            """)
            
            conn.commit()
    
    def log_search(self, analytics: SearchAnalytics) -> None:
        """Record search query in analytics database.
        
        Stores comprehensive search data including results, performance metrics,
        and user information for later analysis.
        
        Args:
            analytics: SearchAnalytics model with complete search data.
        """
        # Check if analytics is enabled
        from ..config import config
        if not config.analytics.enabled:
            return
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO search_analytics 
                    (url, user_id, username, timestamp, platform, success, 
                     item_price, shipping_us, item_title, error_message, 
                     processing_time_ms, seller_score, seller_category,
                     final_price_usd, commission, is_buyable)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    analytics.url,
                    analytics.user_id,
                    analytics.username,
                    analytics.timestamp,
                    analytics.platform,
                    analytics.success,
                    float(analytics.item_price) if analytics.item_price else None,
                    float(analytics.shipping_us) if analytics.shipping_us else None,
                    analytics.item_title,
                    analytics.error_message,
                    analytics.processing_time_ms,
                    analytics.seller_score,
                    analytics.seller_category,
                    float(analytics.final_price_usd) if analytics.final_price_usd else None,
                    float(analytics.commission) if analytics.commission else None,
                    analytics.is_buyable
                ))
                conn.commit()
                
            logger.info(f"Logged search: {analytics.platform} - {analytics.success}")
            
        except Exception as e:
            logger.error(f"Failed to log search analytics: {e}")
    
    def get_daily_stats(self, days: int = 1) -> Dict[str, Any]:
        """Get daily usage statistics.
        
        Args:
            days: Number of days to look back (default: 1 for today).
            
        Returns:
            Dictionary with daily statistics including counts, success rates,
            and platform breakdowns.
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Total searches
                total = conn.execute("""
                    SELECT COUNT(*) as count
                    FROM search_analytics 
                    WHERE timestamp >= ?
                """, (cutoff_date,)).fetchone()
                
                # Success rate
                success = conn.execute("""
                    SELECT COUNT(*) as count
                    FROM search_analytics 
                    WHERE timestamp >= ? AND success = 1
                """, (cutoff_date,)).fetchone()
                
                # Platform breakdown
                platforms = conn.execute("""
                    SELECT platform, COUNT(*) as count
                    FROM search_analytics 
                    WHERE timestamp >= ?
                    GROUP BY platform
                    ORDER BY count DESC
                """, (cutoff_date,)).fetchall()
                
                # Average processing time
                avg_time = conn.execute("""
                    SELECT AVG(processing_time_ms) as avg_ms
                    FROM search_analytics 
                    WHERE timestamp >= ? AND processing_time_ms IS NOT NULL
                """, (cutoff_date,)).fetchone()
                
                return {
                    "total_searches": total["count"],
                    "successful_searches": success["count"],
                    "success_rate": success["count"] / total["count"] if total["count"] > 0 else 0,
                    "platforms": dict(platforms),
                    "avg_processing_time_ms": avg_time["avg_ms"] if avg_time["avg_ms"] else 0,
                    "period_days": days
                }
                
        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return {}
    
    def get_user_stats(
        self,
        user_id: int,
        limit: int = 50,
        days: int | None = None,
    ) -> Dict[str, Any]:
        """Get statistics for specific user.
        
        Args:
            user_id: Telegram user ID.
            limit: Maximum number of recent searches to analyze.
            days: Optional number of days to look back.
            
        Returns:
            Dictionary with user-specific statistics and search history.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # User search history
                query = """
                    SELECT * FROM search_analytics 
                    WHERE user_id = ?
                """
                params: list[Any] = [user_id]

                if days is not None:
                    cutoff = datetime.now() - timedelta(days=days)
                    query += " AND timestamp >= ?"
                    params.append(cutoff)

                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                searches = conn.execute(query, params).fetchall()
                
                if not searches:
                    return {"user_id": user_id, "total_searches": 0}
                
                # Basic stats
                total_searches = len(searches)
                successful_searches = sum(1 for s in searches if s["success"])
                
                # Platform usage
                platforms = {}
                for search in searches:
                    platform = search["platform"]
                    platforms[platform] = platforms.get(platform, 0) + 1
                
                # Average prices
                prices = [float(s["final_price_usd"]) for s in searches 
                         if s["final_price_usd"] is not None]
                avg_price = sum(prices) / len(prices) if prices else 0
                
                return {
                    "user_id": user_id,
                    "username": searches[0]["username"],
                    "total_searches": total_searches,
                    "successful_searches": successful_searches,
                    "success_rate": successful_searches / total_searches,
                    "platforms": platforms,
                    "avg_price_usd": avg_price,
                    "first_search": searches[-1]["timestamp"],
                    "last_search": searches[0]["timestamp"]
                }
                
        except Exception as e:
            logger.error(f"Failed to get user stats for {user_id}: {e}")
            return {"user_id": user_id, "error": str(e)}
    
    def get_popular_items(self, limit: int = 10, days: int = 7) -> List[Dict[str, Any]]:
        """Get most popular searched items.
        
        Args:
            limit: Maximum number of items to return.
            days: Number of days to look back.
            
        Returns:
            List of popular items with search counts and average prices.
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                items = conn.execute("""
                    SELECT 
                        item_title,
                        COUNT(*) as search_count,
                        AVG(final_price_usd) as avg_price,
                        platform
                    FROM search_analytics 
                    WHERE timestamp >= ? 
                        AND success = 1 
                        AND item_title IS NOT NULL
                    GROUP BY item_title, platform
                    ORDER BY search_count DESC
                    LIMIT ?
                """, (cutoff_date, limit)).fetchall()
                
                return [dict(item) for item in items]
                
        except Exception as e:
            logger.error(f"Failed to get popular items: {e}")
            return []
    
    def export_to_csv(self, filename: str, days: Optional[int] = None) -> bool:
        """Export analytics data to CSV file.
        
        Args:
            filename: Output CSV filename.
            days: Number of days to export (None for all data).
            
        Returns:
            True if export successful, False otherwise.
        """
        # Check if export is enabled
        from ..config import config
        if not config.analytics.export_enabled:
            logger.warning("Analytics export is disabled in configuration")
            return False
            
        try:
            import pandas as pd
            
            query = "SELECT * FROM search_analytics"
            params = []
            
            if days:
                cutoff_date = datetime.now() - timedelta(days=days)
                query += " WHERE timestamp >= ?"
                params.append(cutoff_date)
            
            query += " ORDER BY timestamp DESC"
            
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=params)
                df.to_csv(filename, index=False)
                
            logger.info(f"Exported {len(df)} records to {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export to CSV: {e}")
            return False
    
    def get_error_analysis(self, days: int = 7) -> Dict[str, Any]:
        """Analyze common errors and failure patterns.
        
        Args:
            days: Number of days to analyze.
            
        Returns:
            Dictionary with error statistics and common failure patterns.
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Common error messages
                errors = conn.execute("""
                    SELECT 
                        error_message,
                        COUNT(*) as count,
                        platform
                    FROM search_analytics 
                    WHERE timestamp >= ? 
                        AND success = 0 
                        AND error_message IS NOT NULL
                    GROUP BY error_message, platform
                    ORDER BY count DESC
                    LIMIT 10
                """, (cutoff_date,)).fetchall()
                
                # Failure rate by platform
                platform_failures = conn.execute("""
                    SELECT 
                        platform,
                        COUNT(*) as total,
                        SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
                    FROM search_analytics 
                    WHERE timestamp >= ?
                    GROUP BY platform
                """, (cutoff_date,)).fetchall()
                
                return {
                    "common_errors": [dict(error) for error in errors],
                    "platform_failure_rates": [
                        {
                            "platform": p["platform"],
                            "total": p["total"],
                            "failures": p["failures"],
                            "failure_rate": p["failures"] / p["total"]
                        }
                        for p in platform_failures
                    ]
                }
                
        except Exception as e:
            logger.error(f"Failed to get error analysis: {e}")
            return {}


# Create global analytics service instance
analytics_service = AnalyticsService()
