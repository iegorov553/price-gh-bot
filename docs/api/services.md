# Business Services

Core business logic services for external integrations and calculations.

## Currency Service

Exchange rate fetching and conversion using Central Bank of Russia API.

::: app.services.currency

## Shipping Service

Shopfans shipping cost estimation with tiered pricing based on order value and item categorization.

**Features:**
- Dynamic route selection (Europe/Turkey/Kazakhstan) based on order total
- Updated handling fee thresholds (1.36kg instead of 0.45kg)
- Pattern-based weight estimation from item titles

::: app.services.shipping

## Reliability Service

Grailed seller reliability analysis and scoring system.

::: app.services.reliability