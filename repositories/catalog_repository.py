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


def fetch_stores():
    return fetch_all("stores", STORE_COLUMNS)


def fetch_offers_for_product(product_id):
    response = (
        get_supabase_client()
        .table("product_offers")
        .select(OFFER_COLUMNS)
        .eq("product_id", product_id)
        .execute()
    )
    return response.data or []


def fetch_history_for_product(product_id):
    response = (
        get_supabase_client()
        .table("price_history")
        .select(HISTORY_COLUMNS)
        .eq("product_id", product_id)
        .execute()
    )
    return response.data or []
