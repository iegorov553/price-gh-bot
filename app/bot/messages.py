"""Telegram bot message templates and constants.

Contains all user-facing message templates in Russian, error messages, and
formatting constants for bot responses. Centralizes message management for
easy localization and consistent user experience across different bot features.
"""

# Bot commands and descriptions
START_MESSAGE = (
    "Пришлите ссылку на товар с Grailed. Бот рассчитает стоимость с доставкой и комиссией.\n\n"
    "Комиссия: $15 для товаров дешевле $150, или 10% для товаров от $150.\n"
    "Цены показываются в долларах и рублях по курсу ЦБ РФ + 5%."
)

# Error messages
ERROR_PRICE_NOT_FOUND = "Не удалось получить цену товара"
ERROR_SELLER_DATA_NOT_FOUND = "Не удалось получить данные о продавце"
ERROR_SELLER_ANALYSIS = "Ошибка при анализе продавца"

# Site availability messages
GRAILED_SITE_DOWN = (
    "Не удалось получить цену товара.\n\n"
    "🔍 Проверка показала, что сайт Grailed временно недоступен "
    "(HTTP {status_code}, время ответа: {response_time}мс).\n\n"
    "💡 Попробуйте позже - обычно проблемы решаются в течение нескольких часов."
)

GRAILED_SITE_SLOW = (
    "Не удалось получить цену товара.\n\n"
    "🔍 Проверка показала, что сайт Grailed работает медленно "
    "(время ответа: {response_time}мс).\n\n"
    "💡 Попробуйте повторить запрос через несколько минут."
)

GRAILED_LISTING_ISSUE = (
    "Не удалось получить цену товара.\n\n"
    "🔍 Сайт Grailed работает нормально, но возможны проблемы с конкретным листингом:\n"
    "• Товар мог быть удален\n"
    "• Ссылка может быть неактивной\n"
    "• Временные проблемы с загрузкой страницы\n\n"
    "💡 Попробуйте другую ссылку или повторите запрос позже."
)

# Offer-only items message
OFFER_ONLY_MESSAGE = (
    "У продавца не указана цена выкупа. Для расчёта полной стоимости товара необходимо связаться с продавцом.\n\n"
    "Указанная цена: ${price}"
)

# Commission descriptions
COMMISSION_FIXED = "комиссии $15"
COMMISSION_PERCENTAGE = "комиссии 10%"

# Price calculation format - detailed breakdown
PRICE_CALCULATION_HEADER = "💰 Расчёт стоимости"
ITEM_PRICE_LINE = "Товар: ${item_price}"
SHIPPING_US_LINE = "Доставка в США: ${shipping_us}"
SHIPPING_RU_LINE = "Доставка в РФ: ${shipping_ru}"
SHIPPING_ONLY_RU_LINE = "Доставка в РФ: ${shipping_ru} (Shopfans)"
SUBTOTAL_LINE = "Итого: ${subtotal}"
COMMISSION_LINE = "Комиссия: ${commission} ({commission_type})"
SEPARATOR_LINE = "──────────────────"
FINAL_TOTAL_LINE = "Итого к оплате: ${final_price}"
RUB_CONVERSION_LINE = "В рублях: ₽{rub_price}"

# Commission types
COMMISSION_TYPE_FIXED = "фикс. сумма"
COMMISSION_TYPE_PERCENTAGE = "10% от товара"

# Seller reliability categories
SELLER_RELIABILITY = {
    'Diamond': {
        'emoji': '💎',
        'description': 'Продавец топ-уровня, можно брать без лишних вопросов'
    },
    'Gold': {
        'emoji': '🥇',
        'description': 'Надёжный продавец, можно покупать'
    },
    'Silver': {
        'emoji': '🥈',
        'description': 'Нормальный продавец, можно купить или посмотреть альтернативы'
    },
    'Bronze': {
        'emoji': '🥉',
        'description': 'Повышенный риск, возможно стоит поискать другого продавца'
    },
    'Ghost': {
        'emoji': '👻',
        'description': 'Низкая надёжность продавца, высокий риск'
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

# Loading messages
LOADING_MESSAGE = "⏳ Загружаем данные и производим расчёт..."
LOADING_SELLER_ANALYSIS = "⏳ Анализируем профиль продавца..."

# Log messages
LOG_CBR_API_FAILED = "CBR API is unavailable. Currency conversion disabled. Check logs for details."
