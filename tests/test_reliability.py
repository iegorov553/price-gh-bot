"""Tests for Grailed seller reliability evaluation system.

This module contains tests for the seller reliability service that:
- Evaluates sellers across 4 scoring criteria (activity, rating, reviews, badge)
- Categorizes sellers into Diamond/Gold/Silver/Bronze/Ghost tiers
- Handles various seller profile scenarios and edge cases
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.models import SellerData
from app.services.reliability import evaluate_seller_reliability


def test_evaluate_seller_reliability_diamond():
    """Test Diamond tier seller evaluation."""
    seller_data = SellerData(
        num_reviews=250,
        avg_rating=4.95,
        trusted_badge=True,
        last_updated=datetime.now(timezone.utc) - timedelta(days=1)
    )
    
    score = evaluate_seller_reliability(seller_data)
    
    assert score.category == "Diamond"
    assert score.total_score >= 85
    assert score.activity_score == 30
    assert score.rating_score == 35
    assert score.review_volume_score == 25
    assert score.badge_score == 10


def test_evaluate_seller_reliability_gold():
    """Test Gold tier seller evaluation."""
    seller_data = SellerData(
        num_reviews=100,
        avg_rating=4.80,
        trusted_badge=False,
        last_updated=datetime.now(timezone.utc) - timedelta(days=3)
    )
    
    score = evaluate_seller_reliability(seller_data)
    
    assert score.category == "Gold"
    assert 70 <= score.total_score < 85
    assert score.activity_score == 24
    assert score.rating_score == 30
    assert score.review_volume_score == 20
    assert score.badge_score == 0


def test_evaluate_seller_reliability_ghost_inactive():
    """Test Ghost tier for inactive seller."""
    seller_data = SellerData(
        num_reviews=50,
        avg_rating=4.50,
        trusted_badge=True,
        last_updated=datetime.now(timezone.utc) - timedelta(days=35)
    )
    
    score = evaluate_seller_reliability(seller_data)
    
    assert score.category == "Ghost"
    assert score.total_score == 0
    assert score.activity_score == 0
    assert score.rating_score == 0
    assert score.review_volume_score == 0
    assert score.badge_score == 0


def test_evaluate_seller_reliability_bronze():
    """Test Bronze tier seller evaluation."""
    seller_data = SellerData(
        num_reviews=5,
        avg_rating=3.80,
        trusted_badge=False,
        last_updated=datetime.now(timezone.utc) - timedelta(days=15)
    )
    
    score = evaluate_seller_reliability(seller_data)
    
    assert score.category == "Bronze"
    assert 40 <= score.total_score < 55
    assert score.activity_score == 12
    assert score.rating_score == 0
    assert score.review_volume_score == 5
    assert score.badge_score == 0


def test_evaluate_seller_reliability_no_reviews():
    """Test evaluation with no reviews."""
    seller_data = SellerData(
        num_reviews=0,
        avg_rating=0.0,
        trusted_badge=False,
        last_updated=datetime.now(timezone.utc) - timedelta(days=1)
    )
    
    score = evaluate_seller_reliability(seller_data)
    
    assert score.total_score == 30  # Only activity score
    assert score.activity_score == 30
    assert score.rating_score == 0
    assert score.review_volume_score == 0
    assert score.badge_score == 0