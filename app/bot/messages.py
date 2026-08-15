"""Telegram bot message templates and constants.

Contains all user-facing message templates in Russian, error messages, and
formatting constants for bot responses. Centralizes message management for
easy localization and consistent user experience across different bot features.
"""

# Bot commands and descriptions
START_MESSAGE = (
    "Пришлите ссылку на товар с Grailed. Бот рассчитает стоимость с доставкой и комиссией.\n\n"
    "Комиссия: $15 для товаров дешевле $150, или 10% для товаров от $150.\n"
    "Цены показываются в долларах и рублях по курсу ЦБ РФ + 5%.\n\n"
    "Команды:\n"
    "/feedback - отправить отзыв или предложение"
)

# Error messages
ERROR_PRICE_NOT_FOUND = "Не удалось получить цену товара"
ERROR_SELLER_ANALYSIS = "Ошибка при анализе продавца"
ERROR_SELLER_DATA_NOT_FOUND = "Не удалось получить данные о продавце"

# Seller warnings
SELLER_WARNING_LOW_RATING = (
    "⚠️ Я не рекомендую заказывать у этого продавца из-за большого количества негативных отзывов."
)
SELLER_WARNING_NO_REVIEWS = (
    "⚠️ Я не рекомендую заказывать у этого продавца, так как у него отсутствуют отзывы."
)
ITEM_WARNING_NO_BUY_NOW = (
    "⚠️ У продавца не указана цена выкупа — выкупить товара невозможно.\n"
    "Необходимо связаться с продавцом для уточнения наличия/актуальной цены."
)
ITEM_SOLD_MESSAGE = (
    "⚠️ Этот товар уже продан на Grailed (архивное объявление).\n"
    "Выкуп невозможен, расчет стоимости приведен для справки."
)
SELLER_OK_MESSAGE = "Проблем с продавцом не обнаружено, перед выкупом обязательно торгуемся."

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

# Commission descriptions
COMMISSION_FIXED = "комиссии $15"
COMMISSION_PERCENTAGE = "комиссии 10%"

# Price calculation format - grouped by stages
USA_PURCHASE_HEADER = "🛒 ПОКУПКА В США"
ITEM_PRICE_LINE = "• Товар: ${item_price}"
SHIPPING_US_LINE = "• Доставка: ${shipping_us}"
COMMISSION_LINE = "• Комиссия: ${commission} ({commission_type})"
USA_SUBTOTAL_LINE = "└ Сумма: ${subtotal}"

RUSSIA_IMPORT_HEADER = "🛃 ВВОЗ В РОССИЮ"
CUSTOMS_DUTY_LINE = "• Пошлина: ${customs_duty} (>200€)"
SHIPPING_RU_LINE = "• Доставка: ${shipping_ru}"
SHIPPING_ONLY_RU_LINE = "• Доставка: ${shipping_ru} (Shopfans)"
RUSSIA_COSTS_LINE = "└ Расходы: ${additional_costs}"

FINAL_TOTAL_HEADER = "💰 ИТОГО: ${final_price} (₽{rub_price})"
FINAL_TOTAL_LINE_NO_RUB = "💰 ИТОГО: ${final_price}"
NEGOTIATION_NOTE_LINE = (
    "ℹ️ Примечание: итоговая сумма — ориентировочная. Цена не учитывает возможную скидку со стороны продавца.\n"
    "Доставка в РФ по факту может оказаться выше/ниже в зависимости от итогового веса при поступлении на склад.\n"
    "Ожидаемый срок доставки — 2–3 недели."
)
CALCULATION_TIMESTAMP_LINE = "_Расчёт выполнен {datetime} (UTC{offset})_"
CALCULATION_TIMESTAMP_FORMAT = "%d.%m.%Y %H:%M"

# Commission types
COMMISSION_TYPE_FIXED = "фикс. сумма"
COMMISSION_TYPE_PERCENTAGE = "10% от товара+доставка США"

# Admin notification template
ADMIN_NOTIFICATION = "🚨 Price Bot Alert:\n{message}"

# Loading messages
LOADING_MESSAGE = "⏳ Загружаем данные и производим расчёт..."
LOADING_SELLER_ANALYSIS = "⏳ Анализируем профиль продавца..."

# Log messages
LOG_CBR_API_FAILED = "CBR API is unavailable. Currency conversion disabled. Check logs for details."

# Feedback system messages
FEEDBACK_REQUEST_MESSAGE = "Напишите ваше сообщение:"
FEEDBACK_SUCCESS_MESSAGE = "✅ Спасибо за сообщение!"
FEEDBACK_ERROR_MESSAGE = "❌ Не удалось отправить сообщение. Попробуйте позже."
