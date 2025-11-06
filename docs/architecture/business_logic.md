# Business Logic Guide

This document explains how Price GH Bot transforms user input into the pricing and seller advisory insights delivered in Telegram. It focuses on domain services, calculation rules, and the primary user journeys.

## Core User Journeys
- **Listing cost breakdown**  
  1. The user sends one or more eBay or Grailed URLs.  
  2. `url_processor` validates and categorises links.  
  3. `scraping_orchestrator` resolves each item via marketplace scrapers.  
  4. `shipping`, `commission`, `customs`, and `currency` services assemble a `PriceCalculation`.  
  5. `response_formatter` returns a Russian-language price breakdown and optional photos.
- **Grailed seller analysis**  
  1. The user shares a Grailed seller profile link.  
  2. `scraping_orchestrator` triggers the Grailed scraper (Playwright-backed if needed).  
  3. `seller_assessment` service evaluates rating, review volume, and listing data to produce an advisory message.  
  4. The bot responds либо предупреждением, либо кратким подтверждением, что продавец выглядит надёжным.
- **Admin analytics commands**  
  1. Administrators issue `/analytics_*` commands.  
  2. `analytics_service` aggregates data stored in `data/analytics.db`.  
  3. Results are formatted as Markdown or CSV and returned in chat.

The orchestrator handles multiple URLs concurrently, so large batches reach the calculation phase without serial bottlenecks.

## Pricing Pipeline
Once the scraper returns structured `ItemData`, the domain services work in this order:

1. **Commission** (`app/services/commission.py`)  
   - Flat USD 15 when `(item price + US shipping) < USD 150`.  
   - 10 % on higher-value orders.  
   - Commission type is embedded in the resulting `PriceCalculation` for transparency.
2. **Shipping (Shopfans)** (`app/services/shipping.py`)  
   - Estimates parcel weight using keyword patterns from `app/config/shipping_table.yml`.  
   - Applies tiered per‑kilogram routes based on total order value:  
     - `< USD 200` → Europe rate (30.86 USD/kg)  
     - `≥ USD 200` → Turkey rate (35.27 USD/kg)  
     - `≥ USD 1000` → Kazakhstan rate (41.89 USD/kg)  
   - Adds handling fees: USD 3 (≤ 1.36 kg) or USD 5 (> 1.36 kg).  
   - Returns a `ShippingQuote` with weight, cost, and selected route description.
3. **Customs duty** (`app/services/customs.py`)  
   - Converts the 200 EUR personal import threshold into USD using live EUR→USD rates.  
   - Applies a 15 % duty on the excess if `(item price + US shipping) > threshold`.  
   - Duty is rounded to cents and stored in the calculation.
4. **Currency conversion** (`app/services/currency.py`)  
   - Retrieves USD→RUB and EUR→USD rates from the CBR API.  
   - Uses Redis (via `cache_service`) for 12‑hour caching and maintains a local fallback cache.  
   - Adds a configurable markup percentage to USD→RUB to cover exchange costs.  
   - Produces a `CurrencyRate` object used to compute the final RUB total.
5. **Aggregation** (`app/services/calculator.py` or orchestrator utilities)  
   - Combines item price, commission, domestic shipping, customs duty, and Russia delivery into `PriceCalculation`.  
   - Populates `subtotal`, `additional_costs`, `final_price_usd`, and `final_price_rub`.

All intermediate values are Decimal-based to avoid floating-point drift.

## Seller Advisory Rules
`app/services/seller_assessment.py` реализует простые правила, которые подсказывают оператору, стоит ли продолжать сделку:
- **Низкий рейтинг**: если средняя оценка ≤ 4.6 при наличии отзывов, бот сообщает о большом количестве негативных отзывов.  
- **Нет отзывов**: при нулевом количестве отзывов бот предупреждает, что нет подтверждений надёжности.  
- **Нет цены выкупа**: если товар нельзя купить по фиксированной цене, пользователь получает рекомендацию отказаться от покупки.

Когда ни одно из условий не выполняется, ответ ограничивается финальной суммой и напоминанием, что оператор торгуется перед выкупом.

## Analytics Flow
`analytics_tracker` and `analytics_service` capture every interaction:
- URL processing (success/failure, processing time, pricing summary).  
- Seller analysis results (advisory reason/message).  
- Admin command usage and suspicious URL attempts.

Data lands in SQLite (`search_analytics` table) with indexes for time, user, platform, and success fields. Admin commands query this store for daily/weekly statistics, user histories, error patterns, CSV exports, and direct DB downloads.

## Error Handling & Feedback
- `error_boundary` ensures users see user-friendly Russian messages even when scrapers fail.  
- Suspicious URLs are logged without notifying the user.  
- `/feedback` pauses scraping, collects user feedback, and (optionally) opens GitHub issues through `GitHubService`.

## Extending the Logic
To add a new marketplace or pricing rule:
- Implement `ScraperProtocol` and register it in `scraper_registry`.  
- Extend domain services as needed (e.g., new shipping provider).  
- Update `response_formatter` templates for new data fields.  
- Add unit/integration tests that verify new calculations.  
- Document changes here and in the README so administrators understand the new flow.

This layered approach lets the bot evolve while keeping calculations deterministic and transparent to both operators and users.
