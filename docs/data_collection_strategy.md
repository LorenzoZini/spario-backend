# Spario Data Collection Strategy

Strategy document only. This is not an importer implementation plan, not a
schema migration, and not an instruction to run data collection.

## Executive Summary

Spario should collect fewer categories deeply before collecting many categories
shallowly.

The current catalog is structurally clean, but it is not yet deep enough for
strong multi-store comparison or strong buy/wait guidance:

- 194 products
- 195 offers
- 14 stores
- 205 price history rows
- 0 orphan offers
- 0 orphan price history rows
- 0 invalid offer prices
- 0 products without offers
- 0 products without price history
- 65 products have names over 120 characters
- 7 duplicate store-name groups
- 11 stores have no linked offers
- only 1 product currently has multiple offers
- average price history depth is 1.06 points per product
- 189 products are still insufficient for prediction readiness
- 0 products have stronger buy/wait signal
- latest valid price history is stale by the audit threshold

The next data investment should prioritize reliable repeated collection for a
small set of valuable products, not random catalog expansion.

## A. Strategic Principle

Spario is not a simple price comparator or coupon app. The core promise is:

```text
Spario does not only tell the user where it costs less.
It tells the user whether it makes sense to buy now.
```

That promise needs data relationships that stay clean over time:

```text
canonical product -> store offers -> price history -> buy/wait/monitor guidance
```

More products are not useful if:

- the same product is duplicated across canonical records
- different variants are merged incorrectly
- products have only one store offer
- price history is too shallow
- prices are stale
- stores are duplicated or inactive
- product names are too noisy to compare reliably

Data quality matters more than raw quantity because bad data compounds:

- duplicate products split price history
- wrong matches corrupt price history
- stale offers create misleading recommendations
- shallow history makes prediction language untrustworthy
- GPT cannot fix dirty commercial data without inventing facts

The product principle should be:

```text
Depth first, breadth second.
```

## Current Baseline

The audits show a healthy foundation:

- referential integrity is good
- price values are valid
- every product has at least one offer
- every product has at least one history row
- current offer prices match latest comparable history prices

But the catalog is still shallow:

- only 1 product has multiple offers
- most products have only 1 history point
- no product has 10+ valid history points
- most stores are not active in offers
- product titles contain retailer noise

This means Spario can already support product discovery and current-price
answers, but should avoid strong prediction claims until history depth improves.

## MVP Data Needs

The MVP should prove that Spario can do three things reliably:

1. Find real products.
2. Compare real offers across at least 2 stores for important products.
3. Track the same product/store price over time.

MVP data should be small but high-quality:

- 3 to 5 priority categories
- 30 to 80 canonical products per priority category
- 2 active stores for a meaningful subset of products
- 2 to 3 price history points minimum before monitor guidance
- 4 to 9 price history points before weak buy/wait language
- 10+ fresh points before stronger buy/wait language

The MVP should not try to cover the entire Italian electronics market.

## Beta Data Needs

The beta should expand depth, not just count:

- 250 to 500 clean canonical products
- 4 to 6 categories
- 3 active stores for top categories
- 30 to 50 high-priority products with 2+ offers
- 50 to 100 products with 4+ history points
- at least 20 products with 10+ history points
- clear stale-data monitoring
- manual review for uncertain product matches

The beta should make Spario feel useful for selected categories, not complete
for every category.

## Scale-Up Data Needs

Scale-up should happen only after the pipeline proves that it can:

- preserve canonical identity across stores
- avoid variant merge mistakes
- refresh prices repeatedly
- keep collection cost under control
- detect failures and stale data
- grow price history without resetting product identity

Scale-up targets can eventually include:

- thousands of canonical products
- 5+ active stores
- category-specific matching rules
- scheduled collection tiers
- monitoring dashboards
- manual review queue for uncertain matches
- future matching metadata only after schema review

Do not scale catalog size before the matching and history loops are reliable.

## B. MVP Category Focus

Recommended priority order:

1. Smartphones
2. Headphones and earbuds
3. TVs
4. Gaming consoles
5. Gaming accessories
6. Laptops, only after matching improves

### Smartphones

Why useful:

- high user intent
- strong brand/model structure
- prices change meaningfully
- users understand storage/color tradeoffs

Risks:

- storage variants must not be merged
- Pro, Plus, Max, Ultra variants must be preserved
- color can be either separate or grouped depending on future UX choice

Recommendation:

- start with popular Apple, Samsung, Xiaomi, Motorola, OPPO models
- treat storage as a hard differentiator
- treat Pro/Plus/Max/Ultra as hard differentiators

### Headphones and Earbuds

Why useful:

- easier product matching than laptops
- popular price-alert category
- good fit for budget queries

Risks:

- color variants
- bundle names
- similar series names

Recommendation:

- prioritize AirPods, Sony, Bose, JBL, Samsung, Beats
- preserve Max/Pro/model differences
- color can be medium-risk, not automatic merge

### TVs

Why useful:

- high ticket size
- meaningful discounts
- good category for buy/wait guidance

Risks:

- screen size is a hard differentiator
- similar long retailer titles create false matches
- model-year and panel type matter

Recommendation:

- collect fewer TV products, but match carefully
- screen size, model code, OLED/QLED/Mini LED must be preserved

### Gaming Consoles

Why useful:

- easy consumer intent
- high search demand
- fewer core products

Risks:

- disc vs digital
- slim vs original
- bundles vs standalone
- refurbished vs new

Recommendation:

- this is a strong MVP category if clean URLs are available
- never merge bundles with standalone consoles

### Gaming Accessories

Why useful:

- good cross-sell and budget category
- lower matching risk for known SKUs

Risks:

- bundles, colors, editions

Recommendation:

- focus on controllers, headsets, storage, charging docks

### Laptops

Why useful:

- high ticket size
- strong purchase guidance potential

Risks:

- very hard matching
- CPU, RAM, SSD, screen size, model code, year, OS all matter
- long titles are noisy

Recommendation:

- keep laptops limited until matching rules are stronger
- use model codes and specs as required evidence

## C. Store Priority

Recommended store activation order:

1. Unieuro
2. MediaWorld
3. Euronics
4. Comet
5. Trony
6. Amazon, later with caution
7. eBay, later with caution

### Unieuro

Why first:

- already tested
- known collector structure
- relevant Italian electronics retailer

Goal:

- stabilize repeated collection
- improve canonical matching against MediaWorld

### MediaWorld

Why second:

- already partially working
- broad electronics catalog
- critical for real comparison

Goal:

- pair with Unieuro on overlapping products
- increase products with 2 offers

### Euronics

Why third:

- important Italian electronics chain
- useful for coverage and comparison

Goal:

- add after Unieuro and MediaWorld overlap is healthy

### Comet

Why fourth:

- useful regional/Italian retailer coverage
- good for market differentiation

Goal:

- add once matching pipeline is stable enough

### Trony

Why fifth:

- relevant Italian retailer
- useful but should not come before the core stores are stable

Goal:

- add after the main comparison set works

### Amazon and eBay

Use caution:

- Amazon PA API access depends on affiliate constraints
- eBay marketplace data requires stricter filtering
- marketplace offers can include used/refurbished/noisy sellers
- store identity, condition, and listing type must be very clear

Recommendation:

- do not rely on Amazon/eBay for MVP trust
- use them later only with strong filtering and legal/API compliance

## Why Fewer Stores Well Beats Many Stores Poorly

Each additional store increases:

- matching complexity
- duplicate risk
- stale URL risk
- Firecrawl or API cost
- parser maintenance
- monitoring burden

The better near-term goal is:

```text
2 stores deeply on 100 clean products
```

not:

```text
8 stores shallowly on 2,000 noisy products
```

## D. Product Depth Targets

### Initial Clean Beta Set

Recommended target:

- 250 to 500 canonical products
- 4 to 6 categories
- 2 to 3 active stores
- at least 50 products with 2+ offers
- at least 50 products with 4+ history points
- at least 20 products with 10+ history points

### Category Targets

MVP:

- smartphones: 50 to 80 canonical products
- headphones/earbuds: 50 to 80
- TVs: 40 to 60
- gaming consoles/accessories: 20 to 50
- laptops: 20 to 40, only if matching is safe

Beta:

- smartphones: 100+
- headphones/earbuds: 100+
- TVs: 80+
- gaming: 50+
- laptops: 50+, only with stricter matching

### Offers Per Product

Minimum useful comparison:

- 1 offer: discovery only
- 2 offers: basic comparison
- 3+ offers: stronger comparison

Recommendation:

- prioritize getting 2+ offers for the most important 50 products
- do not chase long-tail products before overlap improves

### History Points

Use conservative readiness language:

- 0 to 1 points: insufficient data
- 2 to 3 points: tracking active / monitor only
- 4 to 9 points: weak buy/wait signal
- 10+ points: stronger buy/wait signal

Do not claim prediction accuracy from shallow history.

### Update Cadence

Minimum useful cadence:

- tracked/wishlist products: every 6 to 12 hours
- high-priority products: every 8 to 24 hours
- general catalog: every 24 to 72 hours
- stale or low-value products: weekly or paused

Cadence should depend on budget and collection reliability.

## E. Price History Strategy

Useful price history requires repeated snapshots of the same product/store pair.

Rules:

- keep canonical identity stable
- do not create a new product record for the same item on every import
- write history for the same `product_id` and `store_id`
- keep `condition`, `listing_type`, `data_confidence`, and source fields
  consistent
- exclude low-confidence data from strong prediction logic
- track current offer price against latest history price

Price history should support UX language like this:

- insufficient data: "I do not have enough history yet."
- tracking active: "I am tracking it, but history is still shallow."
- monitor: "Price is not clearly good or bad yet."
- weak signal: "Early history suggests this may be reasonable, but confidence is limited."
- stronger signal: "This price is near the tracked low / above the usual range."

Prediction UX should be conservative until:

- history is fresh
- history has enough points
- product matching is stable
- the best offer store has store-specific history

## F. Product Matching Before Scale

Before inserting more data, every importer should pass through a matching
decision:

1. Normalize title.
2. Extract brand/model/family.
3. Extract hard differentiators.
4. Compare against existing canonical products.
5. If confident, attach offer to existing product.
6. If uncertain, flag for review or create only when safe.

Hard differentiators:

- storage/capacity
- Pro/Plus/Max/Ultra/Mini/Slim variants
- screen size
- model number
- generation/year
- disc vs digital
- bundle vs standalone
- refurbished/used/new
- RAM/SSD/CPU for laptops

Product matching should be conservative:

- HIGH: can be reviewed for future automation
- MEDIUM: manual review
- LOW: do not merge

GPT should not be used to invent matching facts. It can help explain or
structure review later, but the source data must come from retailers and
Supabase.

## G. Import Pipeline Principles

Every future importer should extract:

- product name
- current price
- old price when available
- product URL
- image URL when available
- availability
- store
- category
- condition
- listing type
- data confidence
- source/retailer metadata

Importer rules:

- use `save_product_offer()` or the approved write path only
- avoid direct inserts into canonical products/offers/history
- never overwrite product identity casually
- write price history consistently
- use stable discard reasons
- fail safely without crashing the entire run
- support dry-run before execute
- log success/failure counts
- track cost per valid product/offer
- keep batch sizes conservative

Recommended discard reasons:

- no_title
- no_price
- bad_url
- out_of_stock
- low_confidence
- duplicate_uncertain
- match_conflict
- scrape_error
- search_bad_request

## H. Update Cadence

Use tiers:

### Tier 1: Tracked and Wishlist Products

- refresh every 6 to 12 hours
- prioritize products with alerts or user interest
- keep history fresh

### Tier 2: High-Priority Catalog

- refresh every 8 to 24 hours
- include top smartphones, headphones, TVs, consoles
- focus on products with multiple offers

### Tier 3: General Catalog

- refresh every 24 to 72 hours
- useful for discovery
- less important for prediction

### Tier 4: Stale or Low-Value Products

- refresh weekly or pause
- avoid spending credits on poor-value URLs

Cadence should be adjusted using:

- Firecrawl cost
- valid product yield
- stale history count
- user demand
- category importance

## I. Data Quality Gates

Imported data should pass gates before acceptance:

Required:

- valid price greater than zero
- valid product URL
- mapped store
- valid category
- title present
- product identity not obviously conflicting
- availability parsed
- data confidence assigned

Preferred:

- image URL
- old price
- model code
- SKU/EAN/MPN
- structured data or JSON-LD source
- high-confidence store-specific parser

Flag for review:

- very long titles
- suspiciously similar product names
- missing image
- large price outliers
- conflicting storage/version/screen size
- bundle/refurbished wording
- missing availability

Future user-facing confidence should be simple:

- high confidence: store-specific structured extraction
- medium confidence: reliable pattern extraction
- low confidence: uncertain data, not for prediction

## J. Firecrawl And Budget Strategy

Do not scrape everything blindly.

Firecrawl should be used like a scarce data acquisition budget:

- start with known category pages
- collect known product URLs where possible
- dry-run first
- sample 10 to 30 results before full runs
- inspect discard reasons
- measure cost per valid offer
- stop categories that produce poor yield
- refresh fewer important products consistently

Recommended workflow:

1. Discover URLs in small batches.
2. Scrape a small sample.
3. Measure valid product rate.
4. Review title/price/matching quality.
5. Run a controlled import.
6. Re-run audits.
7. Expand only if quality stays high.

Track:

- search queries tried
- URLs found
- URLs scraped
- products imported
- offers updated
- history rows added
- discard reasons
- cost per valid product
- cost per fresh price update

## K. Metrics To Track

Operational metrics:

- products per category
- offers per product
- products with 2+ offers
- active stores with offers
- stores with no linked offers
- history depth per product
- history depth per product/store
- stale history count
- invalid prices
- orphan offers
- orphan history rows
- duplicate candidate groups
- long product titles
- products with strong prediction readiness
- importer success rate
- importer failure rate
- discard reason distribution
- cost per useful product
- cost per useful price update

North-star data metric:

```text
Products with 2+ offers and 10+ fresh history points
```

This best represents Spario's ability to compare and advise.

## L. Recommended Next Implementation Steps

1. Store cleanup and active store decision
   - decide which store rows are active
   - resolve duplicate store-name groups
   - keep inactive stores out of collection targets

2. Title normalization plan
   - define category-specific normalization
   - preserve hard differentiators
   - reduce long title noise

3. Importer quality checklist
   - require dry-run mode
   - require discard reason logging
   - require confidence assignment
   - require summary metrics

4. Scheduled collection plan
   - start with Unieuro and MediaWorld
   - refresh a limited list every 8 to 24 hours
   - prioritize products with user value

5. Small controlled import expansion
   - add overlap between stores, not random products
   - aim for 2+ offers on top products

6. Monitoring metrics
   - run data quality audit after every controlled import
   - run product matching audit after every category expansion
   - run prediction readiness audit weekly

7. Larger data investment
   - only after duplicate risk, history cadence, and collection cost are known

## M. What NOT To Do Yet

Do not:

- import thousands of products randomly
- expand to too many categories at once
- make strong buy/wait claims without price history
- rely on GPT to fix dirty product data
- launch many stores before quality gates and matching are stable
- overbuild infrastructure before validating the data loop
- scrape broad search results without measuring yield
- merge products automatically
- treat price similarity as enough for product matching
- prioritize long-tail products before overlap on popular products

## Recommended Decision

For the next data phase, Spario should choose:

```text
2 stores, 4 priority categories, 250 to 500 clean products,
with repeated refreshes and strict matching gates.
```

Recommended focus:

- stores: Unieuro + MediaWorld first
- categories: smartphones, headphones/earbuds, TVs, gaming
- optional limited laptops only when model/spec matching is reliable
- goal: increase products with 2+ offers and 4+ history points
- avoid strong prediction UX until products reach 10+ fresh points

This is the fastest path from "catalog exists" to "Spario can give trusted
shopping guidance."

## Next 7 Days Action Plan

Day 1:

- decide active store list
- review duplicate store-name groups
- pick 4 MVP categories

Day 2:

- define top products per category
- prepare known product URL lists where possible
- define dry-run acceptance metrics

Day 3:

- improve title normalization rules on paper
- define hard differentiators per category
- review product matching audit examples

Day 4:

- run small dry-run collection samples only after approval
- measure valid product yield and discard reasons

Day 5:

- run controlled import only if dry-run quality is acceptable
- target overlap between Unieuro and MediaWorld

Day 6:

- run data quality, matching, and prediction readiness audits
- inspect changes in offers per product and history depth

Day 7:

- decide whether to expand category depth or fix importer quality first
- document cost per useful product and price update

## Before Beta Launch Checklist

- [ ] Active store list is clean and intentional.
- [ ] Duplicate store-name groups are resolved or intentionally ignored.
- [ ] Top categories have enough products for useful discovery.
- [ ] Top products have 2+ offers where possible.
- [ ] Scheduled refresh is running reliably.
- [ ] Important products have fresh history.
- [ ] At least some products have 10+ history points.
- [ ] Product matching audit has no obvious high-risk unresolved merges.
- [ ] Data quality audit has no critical integrity issues.
- [ ] Prediction readiness audit supports the UX claims being made.
- [ ] Assistant language is conservative when history is shallow.
- [ ] Firecrawl cost per useful update is known.
- [ ] Importers have dry-run, discard reasons, and safe failure behavior.
- [ ] No strong buy/wait marketing claim is made without enough history.
