"""Сервис рекомендаций по продавцу и товару.

Оценивает данные продавца и карточки товара и возвращает итоговое предупреждение
для пользователя согласно утверждённым правилам:

- Низкий рейтинг (<= 4.6) расценивается как большое количество негативных отзывов.
- Отсутствие отзывов фиксируется отдельным предупреждением.
- Отсутствие цены выкупа приводит к рекомендации отказаться от покупки.
"""

from __future__ import annotations

from ..bot.messages import (
    ITEM_WARNING_NO_BUY_NOW,
    SELLER_WARNING_LOW_RATING,
    SELLER_WARNING_NO_REVIEWS,
)
from ..models import ItemData, SellerAdvisory, SellerData


def evaluate_seller_advisory(
    seller_data: SellerData | None = None,
    item_data: ItemData | None = None,
) -> SellerAdvisory:
    """Сформировать предупреждение для пользователя.

    Args:
        seller_data: Информация о продавце, полученная из скрапера.
        item_data: Информация о товаре, если анализируется карточка.

    Returns:
        SellerAdvisory с заполненным текстом предупреждения или пустым сообщением,
        если все проверки пройдены успешно.
    """
    technical_failure = seller_data is None

    if seller_data:
        if seller_data.technical_issue:
            return SellerAdvisory(
                reason="technical_issue",
                message="Не удалось проанализировать продавца из-за технических проблем, попробуйте позже.",
            )

        if seller_data.num_reviews > 0 and seller_data.avg_rating <= 4.6:
            return SellerAdvisory(reason="low_rating", message=SELLER_WARNING_LOW_RATING)

        if seller_data.num_reviews == 0:
            return SellerAdvisory(reason="no_reviews", message=SELLER_WARNING_NO_REVIEWS)

    if item_data and not item_data.is_buyable:
        return SellerAdvisory(reason="no_buy_now_price", message=ITEM_WARNING_NO_BUY_NOW)

    if technical_failure:
        return SellerAdvisory(
            reason="technical_issue",
            message="Не удалось проанализировать продавца из-за технических проблем, попробуйте позже.",
        )

    return SellerAdvisory()
