# Spario Importer Quality Gates

Documentation only for current behavior. The helper module
`importers/quality_gates.py` is additive and is not wired into existing
collectors by default.

## Why Quality Gates Matter

Spario's data promise depends on clean product identity, valid commercial data,
and repeated price history. Importing more products is not useful if those
products are duplicated, missing prices, missing URLs, category-mismatched, or
too noisy to match safely.

Quality gates let future importers evaluate candidate records before calling
the write path. They support a dry-run-first workflow:

```text
discover candidates -> validate candidates -> inspect dry-run report -> import only approved data
```

This connects directly to:

- Product Contracts: categories and UX claims must stay coherent.
- Product Matching Strategy: differentiators must be preserved.
- Data Collection Strategy: collect fewer products deeply before scaling.
- Price Prediction Readiness: shallow history means conservative guidance.

## Importer Workflow

Future importers should:

1. Extract candidate product/offer data.
2. Run candidate data through `evaluate_candidate()`.
3. Produce a dry-run report with `dry_run_quality_report()`.
4. Review discard reasons and warnings.
5. Import only accepted candidates after explicit approval.
6. Keep all writes routed through the approved write path, currently
   `save_product_offer()`.

Existing collectors are not automatically changed by this document.

## Required Fields

Candidate records should include:

- product name or title
- store identifier, store name, retailer, or source
- current price
- product URL
- category

Critical reject reasons:

- `missing_name`
- `missing_store`
- `missing_price`
- `invalid_price`
- `missing_url`
- `missing_category`

`accepted=false` should be reserved for critical commercial failures. These are
records that should not enter Supabase without correction.

## Recommended Fields

Recommended, non-blocking fields:

- image URL
- availability
- old price
- useful search keywords
- brand/model signals
- source/retailer metadata

Warning codes:

- `missing_image`
- `missing_availability`
- `old_price_lower_than_current_price`
- `title_too_long`
- `title_too_short`
- `generic_title`
- `unknown_category`
- `category_high_matching_complexity`
- `needs_matching_review`
- `possible_bundle_or_condition_variant`
- `important_differentiators_detected`

Warnings mean the record may be usable, but it should be reviewed or treated
with lower confidence.

## Category Mapping Rules

Quality gates normalize messy importer categories to Product Contract keys:

- `smartphone`
- `cuffie`
- `tv`
- `gaming`
- `gaming_accessori`
- `laptop`

MVP categories:

- `smartphone`
- `cuffie`
- `tv`
- `gaming`
- `gaming_accessori`

Laptop is allowed but marked cautious because matching complexity is high.
Unknown categories are flagged with `unknown_category`; they are not silently
accepted as clean data.

## Matching Risk Rules

Candidates get a matching risk:

- `low`
- `medium`
- `high`

Risk increases when:

- title is generic
- brand/model signal is weak
- important differentiators exist
- category is high complexity
- product may be a bundle, refurbished, used, or variant

Important differentiators include:

- storage/capacity
- screen size
- Pro/Max/Ultra/Plus/Mini/Slim
- disc/digital edition
- color
- bundle/refurbished/used/new wording

The gates must detect differentiators and preserve them. They must never merge
products automatically.

## Result Structure

`evaluate_candidate(candidate)` returns:

- `accepted`: boolean
- `severity`: `OK`, `WARNING`, or `CRITICAL`
- `confidence`: `high`, `medium`, or `low`
- `discard_reasons`: machine-readable reject codes
- `warnings`: machine-readable warning codes
- `normalized_category`: clean category key if determinable
- `title_quality`: length, token count, noise, differentiators, brand/model
- `matching_risk`: low/medium/high
- `summary`: short founder-friendly explanation

## Dry-Run Reporting

`dry_run_quality_report(candidates)` returns:

- total candidates
- accepted candidates
- rejected candidates
- candidates with warnings
- counts by discard reason
- counts by warning
- counts by normalized category
- confidence counts
- average confidence label
- limited examples
- founder-friendly summary

The dry-run report intentionally does not print full product URLs by default.

Optional local CLI:

```bash
venv/bin/python -m importers.quality_gates candidates.json
venv/bin/python -m importers.quality_gates candidates.json --json
```

The CLI reads only a local JSON file. It does not call Supabase, Firecrawl,
OpenAI, retailer websites, or external APIs.

## Reporting For Future Importers

Every importer dry-run should report:

- candidates discovered
- candidates accepted
- candidates rejected
- discard reasons
- warnings
- normalized categories
- confidence distribution
- matching risk distribution
- cost per useful offer if Firecrawl or another paid source is used later

## What Not To Do

Do not:

- run mass imports without dry-run
- silently accept unknown categories
- use GPT to clean dirty commercial data
- merge products automatically
- strip differentiators from titles
- ignore old-price inconsistencies
- make strong buy/wait claims from shallow history
- import products with missing URL or invalid price
- treat accepted-with-warning candidates as high-confidence products

## Future Integration

Safe future integration path:

1. Run quality gates inside collectors after extraction and before
   `save_product_offer()`.
2. In dry-run mode, print the report and perform no writes.
3. In execute mode, skip rejected candidates and log warnings.
4. Add matching review before canonical product creation for risky candidates.
5. Track cost per accepted useful offer.

No automatic runtime integration is included in this step.
