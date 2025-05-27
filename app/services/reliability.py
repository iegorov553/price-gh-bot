"""Seller reliability evaluation service."""

from datetime import datetime, timezone

from ..models import SellerData, ReliabilityScore
from ..bot.messages import SELLER_RELIABILITY, GHOST_INACTIVE_DESCRIPTION


def evaluate_seller_reliability(seller_data: SellerData) -> ReliabilityScore:
    """
    Evaluate Grailed seller reliability based on profile metadata.
    
    Args:
        seller_data: SellerData with profile information
    
    Returns:
        ReliabilityScore with evaluation results
    """
    now = datetime.now(timezone.utc)
    last_updated = seller_data.last_updated
    
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)
    
    days_since_update = (now - last_updated).days
    
    # Hard filter: Ghost if inactive > 30 days
    if days_since_update > 30:
        return ReliabilityScore(
            activity_score=0,
            rating_score=0,
            review_volume_score=0,
            badge_score=0,
            total_score=0,
            category='Ghost',
            description=GHOST_INACTIVE_DESCRIPTION
        )
    
    # Activity Score (0-30)
    if days_since_update <= 2:
        activity_score = 30
    elif days_since_update <= 7:
        activity_score = 24
    else:  # 8-30 days
        activity_score = 12
    
    # Rating Score (0-35)
    avg_rating = seller_data.avg_rating
    if avg_rating >= 4.90:
        rating_score = 35
    elif avg_rating >= 4.70:
        rating_score = 30
    elif avg_rating >= 4.50:
        rating_score = 24
    elif avg_rating >= 4.00:
        rating_score = 12
    else:
        rating_score = 0
    
    # Review Volume Score (0-25)
    num_reviews = seller_data.num_reviews
    if num_reviews == 0:
        review_volume_score = 0
    elif num_reviews <= 9:
        review_volume_score = 5
    elif num_reviews <= 49:
        review_volume_score = 15
    elif num_reviews <= 199:
        review_volume_score = 20
    else:  # >= 200
        review_volume_score = 25
    
    # Badge Score (0-10)
    badge_score = 10 if seller_data.trusted_badge else 0
    
    # Total Score
    total_score = activity_score + rating_score + review_volume_score + badge_score
    
    # Determine category and description
    if total_score >= 85:
        category = 'Diamond'
        description = SELLER_RELIABILITY['Diamond']['description']
    elif total_score >= 70:
        category = 'Gold'
        description = SELLER_RELIABILITY['Gold']['description']
    elif total_score >= 55:
        category = 'Silver'
        description = SELLER_RELIABILITY['Silver']['description']
    elif total_score >= 40:
        category = 'Bronze'
        description = SELLER_RELIABILITY['Bronze']['description']
    else:
        category = 'Ghost'
        description = SELLER_RELIABILITY['Ghost']['description']
    
    return ReliabilityScore(
        activity_score=activity_score,
        rating_score=rating_score,
        review_volume_score=review_volume_score,
        badge_score=badge_score,
        total_score=total_score,
        category=category,
        description=description
    )