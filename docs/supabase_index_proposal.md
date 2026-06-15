# Supabase Index Proposal

> **Proposal only - not applied.**
>
> This file is documentation, not an executable migration. None of the SQL
> below has been run against Supabase. Review existing indexes and validate
> query plans before applying any statement.

## Scope

This proposal is limited to the current read patterns in
`repositories/catalog_repository.py` and the product-history reads used by
the assistant. It does not change application behavior, ranking, schema
columns, or API responses.

Current relevant queries:

| Table | Current access pattern |
| --- | --- |
| `products` | `category IN (...)`, bounded `ILIKE '%term%'` across `name`, `search_keywords`, and `category`, ordered by `name, id`, limited to 300 candidates |
| `product_offers` | `product_id = ...` or `product_id IN (...)`, ordered by `product_id, current_price NULLS LAST, id`, paginated |
| `price_history` | `product_id = ...`; rows are currently ordered by `checked_at` in Python |
| `stores` | `id IN (...)` for only the stores referenced by the current offer batch |

The legacy `fetch_products()` fallback still performs a full-table read.
Indexes cannot make an unfiltered full-table read bounded; removing that
fallback safely is a separate application change.

## Existing Index Inventory

Before creating anything, inspect the live database for primary keys, unique
constraints, duplicate indexes, invalid concurrent indexes, and index usage:

```sql
-- Inspection only - run later with appropriate database access.
select
    schemaname,
    tablename,
    indexname,
    indexdef
from pg_indexes
where schemaname = 'public'
  and tablename in (
      'products',
      'product_offers',
      'price_history',
      'stores'
  )
order by tablename, indexname;

select
    relname as table_name,
    indexrelname as index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
from pg_stat_user_indexes
where schemaname = 'public'
  and relname in (
      'products',
      'product_offers',
      'price_history',
      'stores'
  )
order by relname, indexrelname;
```

Expected constraints should be verified rather than assumed:

- `products.id`, `product_offers.id`, `price_history.id`, and `stores.id`
  should already be indexed by their primary keys.
- A unique index on `product_offers(product_id, store_id)` may already exist.
  Its leftmost `product_id` column can help product filtering, but it cannot
  fully support the current price ordering.
- A unique product identity index such as
  `products(category, canonical_key)` may exist, but it does not replace the
  candidate-search indexes proposed below.

## Recommended Indexes

### 1. Exact product category filtering

```sql
-- PROPOSAL ONLY - NOT APPLIED
create index concurrently if not exists idx_products_category
    on public.products (category);
```

Why:

- Supports the repository's `.in_("category", categories)` filter.
- Keeps category candidate reads from scanning the full products table.
- B-tree is appropriate because the filter is exact, not fuzzy.

Tradeoff:

- Categories may have low cardinality. The index is most useful when a
  category selects a reasonably small fraction of a large catalog.
- The database may still sort matching rows by `name, id`.

Optional alternative, to evaluate instead of creating both indexes:

```sql
-- PROPOSAL ONLY - OPTIONAL ALTERNATIVE, NOT APPLIED
create index concurrently if not exists idx_products_category_name_id
    on public.products (category, name, id);
```

This larger index may better serve the common single-category query followed
by `ORDER BY name, id LIMIT 300`. Do not create both category indexes
initially. Compare plans and storage cost, then choose one.

### 2. Product name and keyword substring search

The current candidate query uses leading-wildcard searches such as
`ILIKE '%iphone%'`. Normal B-tree indexes do not accelerate this pattern.
Postgres trigram indexes are the appropriate first step.

```sql
-- PROPOSAL ONLY - NOT APPLIED
create extension if not exists pg_trgm;

create index concurrently if not exists idx_products_name_trgm
    on public.products using gin (name gin_trgm_ops);

create index concurrently if not exists idx_products_search_keywords_trgm
    on public.products using gin (search_keywords gin_trgm_ops);
```

Why:

- Supports case-insensitive substring searches on the two main product text
  fields without introducing a new search service.
- Allows Postgres to combine matching branches with bitmap index scans.
- Keeps the result shape and Python ranking logic unchanged.

Supabase/Postgres notes:

- Confirm whether Supabase installs `pg_trgm` in `public` or `extensions`.
  If the operator class is not found through `search_path`, the reviewed SQL
  may need `extensions.gin_trgm_ops`.
- `CREATE EXTENSION` requires sufficient database privileges.
- Trigram indexes are less effective for search terms shorter than three
  characters, such as `tv`, `lg`, or `hp`.
- GIN indexes increase product insert/update cost and consume additional
  storage, especially for long `search_keywords` values.

The repository also includes `category ILIKE '%term%'` inside its text-search
OR expression. A category trigram index is not in the initial set because
`category` is short and low-cardinality, and exact category searches already
have a B-tree path. If query plans show that the unindexed OR branch forces
sequential scans, evaluate this separately:

```sql
-- PROPOSAL ONLY - OPTIONAL, NOT APPLIED
create index concurrently if not exists idx_products_category_trgm
    on public.products using gin (category gin_trgm_ops);
```

### 3. Batched and deterministically ordered product offers

```sql
-- PROPOSAL ONLY - NOT APPLIED
create index concurrently if not exists idx_product_offers_product_price
    on public.product_offers (
        product_id,
        current_price asc nulls last,
        id
    );
```

Why:

- Matches the leading `product_id` equality/`IN` filter.
- Matches the current deterministic ordering:
  `product_id, current_price NULLS LAST, id`.
- Supports both the single-product and batched offer-read paths.

Tradeoff:

- This overlaps partially with a possible unique index on
  `(product_id, store_id)`. The unique index remains necessary for offer
  identity, while this index is specifically for price-ordered reads.
- Price updates must maintain this index, so write cost will increase.

A separate `product_offers(product_id)` index should not be added if either
the existing unique index or this proposed composite index already provides
the required leading column.

### 4. Product price-history reads

```sql
-- PROPOSAL ONLY - NOT APPLIED
create index concurrently if not exists idx_price_history_product_id
    on public.price_history (product_id);
```

Why:

- The assistant retrieves history using `product_id = ...`.
- Historical rows will grow much faster than the product catalog.
- This index bounds lookup work without changing the current Python-side
  ordering and quality filters.

Possible later replacement, not an additional default index:

```sql
-- PROPOSAL ONLY - FUTURE ALTERNATIVE, NOT APPLIED
create index concurrently if not exists idx_price_history_product_checked_at
    on public.price_history (product_id, checked_at, id);
```

Use the composite alternative if the repository later moves
`ORDER BY checked_at, id` into Postgres. Avoid retaining both indexes unless
measured query plans justify the duplication.

The standalone prediction CLI currently loads the full `price_history` table.
No index can optimize that full scan meaningfully; its data-loading strategy
requires a separate bounded-query refactor.

### 5. Store lookups

No new store index is proposed.

`stores.id` should already be covered by the primary-key index, which is the
correct access path for the current `id IN (...)` lookup. Creating another
index on the same column would add write and storage cost without improving
the query.

## Proposed SQL Bundle

This is the smallest recommended initial set. It is repeated here for review,
not execution:

```sql
-- ================================================================
-- PROPOSAL ONLY - NOT APPLIED
-- Review existing indexes and test in staging before use.
-- CREATE INDEX CONCURRENTLY must not run inside a transaction block.
-- Execute each statement separately.
-- ================================================================

create extension if not exists pg_trgm;

create index concurrently if not exists idx_products_category
    on public.products (category);

create index concurrently if not exists idx_products_name_trgm
    on public.products using gin (name gin_trgm_ops);

create index concurrently if not exists idx_products_search_keywords_trgm
    on public.products using gin (search_keywords gin_trgm_ops);

create index concurrently if not exists idx_product_offers_product_price
    on public.product_offers (
        product_id,
        current_price asc nulls last,
        id
    );

create index concurrently if not exists idx_price_history_product_id
    on public.price_history (product_id);
```

## Performance Verification

Capture a baseline before creating indexes, then repeat the same representative
queries afterward. Use real categories, terms, and product IDs with realistic
row counts.

`EXPLAIN ANALYZE` executes the query. These examples are read-only `SELECT`
statements, but they should still be run deliberately and preferably outside
peak traffic.

```sql
-- Exact category candidates
explain (analyze, buffers, verbose)
select id, name, category, image_url, search_keywords
from public.products
where category in ('tv')
order by name, id
limit 300;

-- Text candidates
explain (analyze, buffers, verbose)
select id, name, category, image_url, search_keywords
from public.products
where name ilike '%iphone%'
   or search_keywords ilike '%iphone%'
   or category ilike '%iphone%'
order by name, id
limit 300;

-- Batched offers; replace UUIDs with representative real product IDs
explain (analyze, buffers, verbose)
select
    id,
    product_id,
    store_id,
    current_price,
    old_price,
    product_url,
    availability,
    condition,
    listing_type,
    data_confidence
from public.product_offers
where product_id in (
    '00000000-0000-0000-0000-000000000001'::uuid,
    '00000000-0000-0000-0000-000000000002'::uuid
)
order by product_id, current_price asc nulls last, id
limit 1000;

-- Product history
explain (analyze, buffers, verbose)
select
    id,
    product_id,
    store_id,
    price,
    checked_at,
    condition,
    listing_type,
    data_confidence
from public.price_history
where product_id = '00000000-0000-0000-0000-000000000001'::uuid;
```

Look for:

- `Index Scan`, `Index Only Scan`, or `Bitmap Index Scan` using the intended
  index.
- Reduced shared-buffer reads and execution time.
- Fewer rows removed by filters.
- Whether a sort remains and how much memory/time it uses.
- Whether short or broad text terms still select too much of the catalog.

After creation, refresh planner statistics if needed:

```sql
-- PROPOSAL ONLY - NOT APPLIED
analyze public.products;
analyze public.product_offers;
analyze public.price_history;
```

## Rollout Plan

1. Inventory current indexes and confirm primary/unique constraints.
2. Capture baseline plans for representative small, medium, and broad queries.
3. Test the proposal on a staging or restored production-like database.
4. Enable `pg_trgm` after confirming its schema and privileges.
5. Create one index at a time during low traffic.
6. Run each `CREATE INDEX CONCURRENTLY` as a separate autocommit statement.
   Do not place these statements inside a transaction-wrapped migration.
7. Monitor database CPU, I/O, storage, lock waits, and index-build progress.
8. Re-run the same `EXPLAIN (ANALYZE, BUFFERS)` queries.
9. Keep only indexes that produce a material improvement.
10. Observe collector write latency after adding GIN and offer-price indexes.

Concurrent builds reduce blocking but still consume CPU, I/O, and temporary
disk space. A failed concurrent build can leave an invalid index that must be
identified and dropped before retrying.

Useful progress and validity checks:

```sql
-- Inspection only
select * from pg_stat_progress_create_index;

select
    indexrelid::regclass as index_name,
    indisvalid,
    indisready
from pg_index
where indexrelid::regclass::text in (
    'idx_products_category',
    'idx_products_name_trgm',
    'idx_products_search_keywords_trgm',
    'idx_product_offers_product_price',
    'idx_price_history_product_id'
);
```

## Risks and Tradeoffs

- Every index consumes storage and increases insert/update maintenance.
- GIN indexes can materially slow updates to searchable text fields.
- The offers index is maintained whenever `current_price` changes.
- Low-selectivity category values may still favor sequential scans.
- Leading-wildcard `ILIKE` remains less capable than a purpose-built search
  model for typo tolerance, language stemming, and weighted fields.
- Trigram indexes may not help two-character brand/category searches.
- Indexes do not solve the legacy full-table product fallback or the
  prediction CLI's full-dataset loading.
- Index creation on a large production table can take significant time even
  with `CONCURRENTLY`.

## Rollback Plan

Drop only indexes proven unnecessary or harmful. Run concurrent drops as
separate autocommit statements, outside transaction blocks:

```sql
-- PROPOSAL ONLY - NOT APPLIED
drop index concurrently if exists public.idx_products_category;
drop index concurrently if exists public.idx_products_name_trgm;
drop index concurrently if exists public.idx_products_search_keywords_trgm;
drop index concurrently if exists public.idx_product_offers_product_price;
drop index concurrently if exists public.idx_price_history_product_id;
```

Optional indexes, if ever tested, should use matching rollback statements:

```sql
-- PROPOSAL ONLY - NOT APPLIED
drop index concurrently if exists public.idx_products_category_name_id;
drop index concurrently if exists public.idx_products_category_trgm;
drop index concurrently if exists public.idx_price_history_product_checked_at;
```

Do not drop `pg_trgm` as part of normal rollback. Other database objects may
depend on the extension. Consider removing it only after checking dependencies
and confirming that no trigram indexes remain.
