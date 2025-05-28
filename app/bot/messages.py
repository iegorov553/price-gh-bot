"""Telegram bot message templates and constants.

Contains all user-facing message templates in Russian, error messages, and
formatting constants for bot responses. Centralizes message management for
easy localization and consistent user experience across different bot features.
"""

# Bot commands and descriptions
START_MESSAGE = (
    "Пришлите ссылку на товар с eBay или Grailed. Бот рассчитает стоимость с доставкой и комиссией.\n\n"
    "Комиссия: $15 для товаров дешевле $150, или 10% для товаров от $150.\n"
    "Цены показываются в долларах и рублях по курсу ЦБ РФ + 5%."
)

# Error messages
ERROR_PRICE_NOT_FOUND = "Не удалось получить цену товара"
ERROR_SELLER_DATA_NOT_FOUND = "Не удалось получить данные о продавце"
ERROR_SELLER_ANALYSIS = "Ошибка при анализе продавца"

# Offer-only items message
OFFER_ONLY_MESSAGE = (
    "У продавца не указана цена выкупа. Для расчёта полной стоимости товара необходимо связаться с продавцом.\n\n"
    "Указанная цена: ${price}"
)

# Commission descriptions
COMMISSION_FIXED = "комиссии $15"
COMMISSION_PERCENTAGE = "комиссии 10%"

# Price calculation format
PRICE_LINE = "Цена: ${price}{shipping_text} = ${total_cost}"
FINAL_PRICE_LINE = "С учетом {commission_text}: ${final_price}{rub_text}"

# Seller reliability categories
SELLER_RELIABILITY = {
    'Diamond': {
        'emoji': '💎',
        'description': 'Продавец топ-уровня, можно брать без лишних вопросов'
    },
    'Gold': {
        'emoji': '🥇',
        'description': 'Высокая надёжность, смело оплачивать'
    },
    'Silver': {
        'emoji': '🥈',
        'description': 'Нормально, но проверь детали сделки'
    },
    'Bronze': {
        'emoji': '🥉',
        'description': 'Повышенный риск, используй безопасную оплату'
    },
    'Ghost': {
        'emoji': '👻',
        'description': 'Низкая надёжность, высокий риск'
    },
    'No Data': {
        'emoji': 'ℹ️',
        'description': 'Данные продавца недоступны (Grailed ограничивает доступ)'
    }
}

# Seller profile analysis
SELLER_PROFILE_HEADER = "Анализ продавца Grailed"
SELLER_RELIABILITY_LINE = "Надёжность: {emoji} {category} ({total_score}/100)"
SELLER_DETAILS_HEADER = "Детали:"
SELLER_ACTIVITY_LINE = "• Активность: {activity_score}/30 (обновления {last_update_text})"
SELLER_RATING_LINE = "• Рейтинг: {rating_score}/35 ({avg_rating:.1f}/5.0)"
SELLER_REVIEWS_LINE = "• Отзывы: {review_volume_score}/25 ({num_reviews} отзывов)"
SELLER_BADGE_LINE = "• Бейдж: {badge_score}/10 ({badge_text})"

# Badge status
TRUSTED_SELLER_BADGE = "Проверенный продавец"
NO_BADGE = "Нет бейджа"

# Time descriptions
TIME_TODAY = "сегодня"
TIME_YESTERDAY = "вчера"
TIME_DAYS_AGO = "{days} дн. назад"

# Seller info in price response
SELLER_INFO_LINE = "Продавец: {emoji} {category} ({total_score}/100)"
SELLER_DESCRIPTION_LINE = "{description}"

# Admin notification template
ADMIN_NOTIFICATION = "🚨 Price Bot Alert:\n{message}"

# Ghost category specific description
GHOST_INACTIVE_DESCRIPTION = "Неактивный продавец (>30 дней без обновлений)"

# Log messages
LOG_CBR_API_FAILED = "CBR API is unavailable. Currency conversion disabled. Check logs for details."
