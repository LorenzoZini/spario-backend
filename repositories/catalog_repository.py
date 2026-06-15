import re

from core.supabase_client import get_supabase_client


PRODUCT_COLUMNS = "id,name,category,image_url,search_keywords"
OFFER_COLUMNS = (
    "id,product_id,store_id,current_price,old_price,product_url,"
    "availability,condition,listing_type,data_confidence"
)
OFFER_FIRST_COLUMNS = (
    "id,product_id,current_price,old_price,availability,"
    "condition,listing_type,data_confidence"
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
PRODUCT_ID_CHUNK_SIZE = 100
OFFER_PAGE_SIZE = DEFAULT_PAGE_SIZE
PRODUCT_CANDIDATE_LIMIT = 300
PRODUCT_SEARCH_TERM_LIMIT = 12
# Offer-first inspects at most 200 offers and forwards at most 80 products.
OFFER_FIRST_ROW_LIMIT = 200
OFFER_FIRST_PRODUCT_LIMIT = 80


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


def fetch_products_by_ids(product_ids):
    unique_product_ids = list(dict.fromkeys(
        product_id
        for product_id in product_ids
        if isinstance(product_id, str) and product_id.strip()
    ))

    if not unique_product_ids:
        return []

    client = get_supabase_client()
    products_by_id = {}

    for product_id_chunk in _chunked(
        unique_product_ids,
        PRODUCT_ID_CHUNK_SIZE,
    ):
        response = (
            client.table("products")
            .select(PRODUCT_COLUMNS)
            .in_("id", product_id_chunk)
            .order("id")
            .execute()
        )
        for product in response.data or []:
            product_id = product.get("id")
            if product_id:
                products_by_id[product_id] = product

    return [
        products_by_id[product_id]
        for product_id in unique_product_ids
        if product_id in products_by_id
    ]


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


def _parse_offer_price(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _offer_first_row_is_usable(offer):
    current_price = _parse_offer_price(offer.get("current_price"))
    if current_price is None or current_price <= 0:
        return False

    availability = str(offer.get("availability") or "").strip().lower()
    if availability in {"out_of_stock", "non disponibile", "esaurito"}:
        return False

    confidence = offer.get("data_confidence")
    if confidence and confidence not in {"alta", "media"}:
        return False

    condition = offer.get("condition")
    if condition and condition != "new":
        return False

    return True


def fetch_offer_first_product_ids(
    reason,
    budget=None,
    row_limit=OFFER_FIRST_ROW_LIMIT,
    product_limit=OFFER_FIRST_PRODUCT_LIMIT,
):
    if reason not in {"discount", "budget"}:
        return []

    try:
        bounded_row_limit = min(
            OFFER_FIRST_ROW_LIMIT,
            max(1, int(row_limit)),
        )
        bounded_product_limit = min(
            OFFER_FIRST_PRODUCT_LIMIT,
            max(1, int(product_limit)),
        )
    except (TypeError, ValueError):
        return []

    budget_value = None
    if reason == "budget":
        budget_value = _parse_offer_price(budget)
        if budget_value is None or budget_value <= 0:
            return []

    query = (
        get_supabase_client()
        .table("product_offers")
        .select(OFFER_FIRST_COLUMNS)
        .gt("current_price", 0)
    )

    if reason == "discount":
        query = (
            query
            .gt("old_price", 0)
            .order("old_price", desc=True, nullsfirst=False)
            .order("current_price", nullsfirst=False)
            .order("id")
        )
    else:
        query = (
            query
            .lte("current_price", budget_value)
            .order("current_price", nullsfirst=False)
            .order("id")
        )

    response = query.limit(bounded_row_limit).execute()
    offers = [
        offer
        for offer in response.data or []
        if _offer_first_row_is_usable(offer)
    ]

    if reason == "discount":
        discounted_offers = []
        for offer in offers:
            current_price = _parse_offer_price(offer.get("current_price"))
            old_price = _parse_offer_price(offer.get("old_price"))
            if (
                current_price is None
                or old_price is None
                or old_price <= current_price
            ):
                continue

            discount_pct = ((old_price - current_price) / old_price) * 100
            discounted_offers.append((
                -discount_pct,
                current_price,
                str(offer.get("id") or ""),
                offer,
            ))

        discounted_offers.sort(key=lambda item: item[:3])
        offers = [item[3] for item in discounted_offers]

    product_ids = []
    seen_product_ids = set()

    for offer in offers:
        product_id = offer.get("product_id")
        if (
            not isinstance(product_id, str)
            or not product_id.strip()
            or product_id in seen_product_ids
        ):
            continue

        product_ids.append(product_id)
        seen_product_ids.add(product_id)

        if len(product_ids) >= bounded_product_limit:
            break

    return product_ids


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
