"""Unit tests for seller advisory logic."""

from decimal import Decimal

from app.bot.messages import (
    ITEM_WARNING_NO_BUY_NOW,
    SELLER_WARNING_LOW_RATING,
    SELLER_WARNING_NO_REVIEWS,
)
from app.models import ItemData, SellerData
from app.services.seller_assessment import evaluate_seller_advisory


def test_low_rating_triggers_warning() -> None:
    """Sellers с рейтингом <= 4.6 и отзывами должны выдавать предупреждение."""
    seller = SellerData(num_reviews=25, avg_rating=4.6)

    advisory = evaluate_seller_advisory(seller_data=seller)

    assert advisory.reason == "low_rating"
    assert advisory.message == SELLER_WARNING_LOW_RATING


def test_no_reviews_triggers_warning() -> None:
    """Отсутствие отзывов формирует отдельное предупреждение."""
    seller = SellerData(num_reviews=0, avg_rating=0.0)

    advisory = evaluate_seller_advisory(seller_data=seller)

    assert advisory.reason == "no_reviews"
    assert advisory.message == SELLER_WARNING_NO_REVIEWS


def test_missing_buy_now_price_triggers_warning() -> None:
    """Отсутствие цены выкупа возвращает предупреждение без расчётов."""
    item = ItemData(price=Decimal("120.00"), is_buyable=False)

    advisory = evaluate_seller_advisory(item_data=item)

    assert advisory.reason == "no_buy_now_price"
    assert advisory.message == ITEM_WARNING_NO_BUY_NOW


def test_no_warning_when_conditions_not_met() -> None:
    """Если все проверки пройдены, предупреждение отсутствует."""
    seller = SellerData(num_reviews=15, avg_rating=4.8)
    item = ItemData(price=Decimal("200.00"), is_buyable=True)

    advisory = evaluate_seller_advisory(seller_data=seller, item_data=item)

    assert advisory.reason is None
    assert advisory.message is None


def test_technical_issue_when_seller_data_missing() -> None:
    """Если данные продавца не получены, пользователь видит сообщение о технической проблеме."""
    item = ItemData(price=Decimal("50"), is_buyable=True)
    advisory = evaluate_seller_advisory(seller_data=None, item_data=item)

    assert advisory.reason == "technical_issue"
    assert "технических проблем" in (advisory.message or "")


def test_technical_issue_flag_overrides_num_reviews() -> None:
    """technical_issue флаг должен иметь приоритет над числом отзывов."""
    seller = SellerData(
        num_reviews=0,
        avg_rating=5.0,
        trusted_badge=True,
        technical_issue=True,
    )
    advisory = evaluate_seller_advisory(seller_data=seller, item_data=ItemData(price=Decimal("10")))

    assert advisory.reason == "technical_issue"
