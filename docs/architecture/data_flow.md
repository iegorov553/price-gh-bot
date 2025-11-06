# Request Data Flow

The following sequence shows how a user message becomes a fully priced response. It covers listing processing; seller profile requests follow the same steps but with different scrapers and formatters.

```text
User sends message with URL
        |
        v
Telegram update arrives at handler
        |
        v
`url_processor` finds valid marketplace URLs
        |
        v
`scraping_orchestrator` schedules tasks
        |
        v
Scrapers fetch data (Playwright or HTTP)
        |
        v
Services calculate shipping, customs, commission
        |
        v
`response_formatter` builds Markdown reply
        |
        v
Telegram bot sends message (with photo if available)
        |
        v
Analytics service logs outcome to SQLite
```

## Detailed Steps
1. **Message handling**  
   - `handlers.handle_link` receives text messages.  
   - Feedback conversations take precedence; normal processing pauses until feedback completes.  
   - Suspicious URLs (unsupported domains, malformed links) trigger analytics events but no user-visible reply.

2. **URL categorisation**  
   - `url_processor` returns a structure separating item listings from seller profiles.  
   - Shortlinks (e.g., `grailed.app.link`) are resolved to canonical URLs before scraping.

3. **Scraping orchestration**  
   - `scraping_orchestrator.process_urls_concurrent` builds asyncio tasks for each URL.  
   - A timeout guard prevents hung Playwright sessions from blocking the whole batch.  
   - Successful results carry raw marketplace data plus timing metadata.

4. **Business calculations**  
   - `services.shipping` selects a route based on total value and weight (with fallback defaults).  
   - `services.customs` applies the 200 EUR threshold and 15 percent duty when exceeded.  
   - `services.commission` enforces flat vs percentage commission rules.  
   - `services.currency` provides USD<->RUB and EUR<->USD conversions with optional markup and caching.

5. **Response formatting**  
   - `response_formatter` composes Markdown using templates from `messages.py`.  
   - If an item image URL is available, the handler sends a photo with the caption; otherwise it posts text only.  
   - Seller profiles return either an advisory warning or a short confirmation when no issues are detected.

6. **Analytics and logging**  
   - `analytics_tracker` records timing, platform, and status flags.  
   - `services.analytics` persists the event, updates aggregates, and exposes admin reports.  
   - Errors are routed through the error boundary to ensure users see a friendly message while admins can investigate logs.

7. **Admin monitoring**  
   - Admin commands query the analytics service for daily, weekly, per-user, or error-focused reports.  
   - CSV exports and database dumps help with deeper offline analysis.

This flow keeps network, pricing, and presentation concerns separated so each piece can evolve independently (e.g., swapping shipping providers or adding new marketplaces).
