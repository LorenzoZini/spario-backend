# Spario Price Prediction Readiness

Proposal and audit notes only. This document does not apply schema changes,
does not change prediction behavior, and does not authorize stronger UX claims.

## Why This Matters

Spario's product promise is not just "find the lowest price." The important
question is whether the user should buy now, wait, monitor, or choose another
product. That requires clean and sufficiently deep price history.

With shallow history, Spario can still be useful as a deal finder and price
monitor. It should not present strong buy/wait guidance until the data supports
that confidence.

## Current Prediction Module

The current module is `predictions/price_predictor.py`.

It can produce these recommendations:

- `insufficient_data`
- `buy_now`
- `wait`
- `monitor`

The module expects:

- products with `id`, `name`, `category`
- offers with `product_id`, `store_id`, `current_price`, `availability`,
  `condition`, `listing_type`, `data_confidence`
- stores with `id`, `name`
- price history with `product_id`, `store_id`, `price`, `checked_at`,
  `condition`, `listing_type`, `data_confidence`

Important implementation detail: prediction history is grouped by
`(product_id, store_id)`, not only by product. That means a product can have
some product-level history but still be weak for the current best store offer.

The default minimum history threshold is currently 3 valid history points. The
module reads Supabase through the centralized client. It does not need GPT and
must not invent history or prices.

## Conservative Readiness Buckets

The audit uses conservative data-readiness buckets:

- `insufficient_data`: 0-1 valid history points
- `monitor_only`: 2-3 valid history points
- `weak_buy_wait_guidance`: 4-9 valid history points
- `stronger_buy_wait_guidance`: 10+ valid history points

These buckets are not accuracy claims. They only describe whether the current
history depth is enough to support different levels of UX confidence.

## Data Quality Checks

The readiness audit should inspect:

- total history rows
- products with and without history
- average and median history depth
- max history depth
- invalid or missing prices
- orphan history rows
- repeated identical price points
- products with no price variation
- current offer price vs latest comparable history price
- oldest and newest history timestamps
- recent vs stale history coverage when timestamps exist

## UX Guidance

Until history depth improves:

- prefer "monitor this" language for shallow products
- show current best price honestly
- avoid confident "buy now" or "wait" claims when history is shallow
- disclose limited history in the assistant answer
- use alerts and tracking as the main user promise

## Recommended Next Steps

1. Keep collecting price snapshots on a schedule.
2. Track history per product and store consistently.
3. Prioritize history depth for popular products and products with multiple
   retailer offers.
4. Review products where current offer price differs from latest history.
5. Consider future schema only after observing enough real history, such as
   model confidence, prediction version, or match confidence.
6. Avoid strong buy/wait UX language until enough products reach 10+ usable
   history points.
