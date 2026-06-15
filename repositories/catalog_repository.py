import re

from core.supabase_client import get_supabase_client


PRODUCT_COLUMNS = "id,name,category,image_url,search_keywords"
OFFER_COLUMNS = (
    "id,product_id,store_id,current_price,old_price,product_url,"
    "availability,condition,listing_type,data_confidence"
)
STORE_COLUMNS = "id,name,website"
HISTORY_COLUMNS = (
    "id,product_id,store_id,price,checked_at,condition,"
    "listing_type,data_confidence"
)

DEFAULT_PAGE_SIZE = 1000
# Conservative bound to keep PostgREST `in` filters well below URL/query limits.
OFFER_PRODUCT_ID_CHUNK_SIZE = 100
STORE_ID_CHUNK_SIZE = 100
OFFER_PAGE_SIZE = DEFAULT_PAGE_SIZE
PRODUCT_CANDIDATE_LIMIT = 300
PRODUCT_SEARCH_TERM_LIMIT = 12


def _chunked(values, chunk_size):
    for start in range(0, len(values), chunk_size):
        yield values[start:start + chunk_size]


def _clean_search_term(value):
    if not isinstance(value, str):
        return ""

    cleaned = re.sub(r"[^\w\s-]", " ", value, flags=re.UNICODE)
    cleaned = cleaned.replace("_", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def fetch_all(table_name, columns, page_size=DEFAULT_PAGE_SIZE):
    client = get_supabase_client()
    rows = []
    start = 0

    while True:
        response = (
            client.table(table_name)
            .select(columns)
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)

        if len(batch) < page_size:
            break

        start += page_size

    return rows


def fetch_products():
    return fetch_all("products", PRODUCT_COLUMNS)


def fetch_candidate_products(
    category_values=None,
    search_terms=None,
    limit=PRODUCT_CANDIDATE_LIMIT,
):
    categories = list(dict.fromkeys(
        category.strip()
        for category in (category_values or [])
        if isinstance(category, str) and category.strip()
    ))
    terms = list(dict.fromkeys(
        cleaned
        for term in (search_terms or [])
        if (cleaned := _clean_search_term(term))
    ))[:PRODUCT_SEARCH_TERM_LIMIT]

    if not categories and not terms:
        return []

    try:
        bounded_limit = min(PRODUCT_CANDIDATE_LIMIT, max(1, int(limit)))
    except (TypeError, ValueError):
        bounded_limit = PRODUCT_CANDIDATE_LIMIT

    query = (
        get_supabase_client()
        .table("products")
        .select(PRODUCT_COLUMNS)
    )

    if categories:
        query = query.in_("category", categories)

    if terms:
        filters = []
        for term in terms:
            pattern = f"%{term}%"
            filters.extend([
                f"name.ilike.{pattern}",
                f"search_keywords.ilike.{pattern}",
                f"category.ilike.{pattern}",
            ])
        query = query.or_(",".join(filters))

    response = (
        query
        .order("name")
        .order("id")
        .limit(bounded_limit)
        .execute()
    )
    return response.data or []


def fetch_stores():
    return fetch_all("stores", STORE_COLUMNS)


def fetch_stores_by_ids(store_ids):
    unique_store_ids = list(dict.fromkeys(
        store_id
        for store_id in store_ids
        if isinstance(store_id, str) and store_id.strip()
    ))

    if not unique_store_ids:
        return []

    client = get_supabase_client()
    stores = []

    for store_id_chunk in _chunked(unique_store_ids, STORE_ID_CHUNK_SIZE):
        response = (
            client.table("stores")
            .select(STORE_COLUMNS)
            .in_("id", store_id_chunk)
            .execute()
        )
        stores.extend(response.data or [])

    return stores


def build_store_lookup(stores):
    return {
        store.get("id"): store
        for store in stores
    }


def fetch_offers_for_product(product_id):
    response = (
        get_supabase_client()
        .table("product_offers")
        .select(OFFER_COLUMNS)
        .eq("product_id", product_id)
        .execute()
    )
    return response.data or []


def fetch_offers_for_product_ids(product_ids):
    unique_product_ids = list(dict.fromkeys(
        product_id
        for product_id in product_ids
        if isinstance(product_id, str) and product_id.strip()
    ))

    if not unique_product_ids:
        return []

    client = get_supabase_client()
    offers = []

    for product_id_chunk in _chunked(
        unique_product_ids,
        OFFER_PRODUCT_ID_CHUNK_SIZE,
    ):
        start = 0

        while True:
            response = (
                client.table("product_offers")
                .select(OFFER_COLUMNS)
                .in_("product_id", product_id_chunk)
                .order("product_id")
                .order("current_price", nullsfirst=False)
                .order("id")
                .range(start, start + OFFER_PAGE_SIZE - 1)
                .execute()
            )
            batch = response.data or []
            offers.extend(batch)

            if len(batch) < OFFER_PAGE_SIZE:
                break

            start += OFFER_PAGE_SIZE

    return offers


def fetch_history_for_product(product_id):
    response = (
        get_supabase_client()
        .table("price_history")
        .select(HISTORY_COLUMNS)
        .eq("product_id", product_id)
        .execute()
    )
    return response.data or []
