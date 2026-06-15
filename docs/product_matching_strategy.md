# Spario Product Matching Strategy

Proposal only. This document describes a read-only product matching strategy for
Spario. It does not apply database changes and does not authorize automatic
merges.

## What Product Matching Means

Product matching is the process of deciding whether two retailer listings refer
to the same real-world product. In Spario, the desired model is:

```text
canonical product -> multiple store offers -> coherent price history -> buy/wait guidance
```

Matching is not just deduplication. It is the foundation for trustworthy
comparison and purchase advice. If Spario splits the same product into many
records, users lose multi-store comparison. If Spario merges different products,
price history and recommendations become misleading.

## Why It Matters

Spario is not a simple product list. It should help a user decide whether to buy
now, wait, monitor, or choose an alternative. That requires:

- one canonical product identity for equivalent offers
- offers from multiple stores attached to that identity
- price history that describes the same product over time
- clear confidence when the system is not sure

## Why Automatic Merging Is Risky

Consumer electronics names contain subtle but commercially important
differences. A match that looks obvious from long titles can still be wrong.

Never merge automatically when the products differ by:

- storage or capacity, such as 128GB vs 256GB
- Pro vs non-Pro
- Max, Plus, Ultra, Mini, Slim or similar variants
- disc vs digital console editions
- screen size
- bundle vs standalone product
- refurbished, renewed or used vs new
- generation, year or model number
- important category-specific specs

Examples:

- iPhone 15 128GB is not the same as iPhone 15 256GB.
- iPhone 15 is not the same as iPhone 15 Pro.
- PS5 Slim Disc is not the same as PS5 Digital.
- AirPods Pro are not the same as AirPods Max.

## Recommended Matching Signals

Strong signals:

- normalized product name
- same category
- brand, if available or inferable
- model/family tokens, such as iPhone 15, AirPods Max, Galaxy S24, PS5
- storage/capacity
- version/generation
- SKU, EAN, GTIN or MPN when available in the future

Supporting signals:

- color
- screen size
- store relationship
- offer count
- similar current prices

Weak signals:

- price similarity alone
- shared generic words such as smartphone, cuffie, notebook or offerta
- long-title overlap caused by marketing copy

Price similarity should never be the main merge signal. It can support a
candidate after identity signals already agree.

## Confidence Levels

HIGH:

- very likely the same product
- same category
- same normalized or highly similar title
- same brand/model tokens
- no important differentiator conflicts

MEDIUM:

- possible duplicate
- same category and partially matching brand/model tokens
- wording differs enough to require review
- weak or non-critical differentiator mismatch, such as color

LOW:

- similar products but insufficient evidence
- important differentiator conflict
- title similarity is probably caused by generic words
- should not be merged without manual review

## Future Architecture

Recommended future flow:

1. Importer extracts raw retailer product/offering data.
2. Matching pipeline searches for existing canonical products.
3. Matching pipeline returns candidates with confidence and reasons.
4. HIGH confidence can be reviewed for automation only after enough validation.
5. MEDIUM and LOW confidence should go to manual review.
6. `product_offers` should link to canonical products only after match approval.
7. Matching confidence and source evidence can be stored in the future only
   after an explicit schema decision.

Do not add matching metadata to the live schema until the matching rules have
been tested against real imports from several retailers.

## Read-Only Phase

The current phase should only:

- inspect existing products and offers
- find possible duplicate/equivalent products
- count confidence levels
- identify risky patterns
- produce examples for manual review

It must not update, merge, delete or rewrite any product, offer, store or price
history data.

## Proposed Next Steps

1. Run `scripts/product_match_audit.py` regularly after imports.
2. Review HIGH and MEDIUM candidates manually.
3. Improve normalization and differentiator extraction by category.
4. Add SKU/EAN/MPN extraction in importers where retailers expose it.
5. Add a manual review workflow before any future merge automation.
6. Only after review data is reliable, propose schema additions for matching
   evidence and confidence.
