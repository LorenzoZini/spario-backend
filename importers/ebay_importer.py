
import base64
import requests
from importers.config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET
from importers.utils import save_product_offer

EBAY_STORE_NAME = "eBay"
EBAY_STORE_WEBSITE = "https://www.ebay.it"
EBAY_STORE_TYPE = "marketplace"

MIN_SELLER_FEEDBACK = 98.0


def get_ebay_token():
    credentials = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()

    response = requests.post(
        "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded}",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
    )

    response.raise_for_status()
    return response.json()["access_token"]


def search_ebay_products(query, limit=20):
    token = get_ebay_token()

    response = requests.get(
        "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params={
            "q": query,
            "limit": limit,
            "buyingOptions": "FIXED_PRICE",
            "filter": "conditions:{NEW}",
        },
    )

    response.raise_for_status()
    return response.json().get("itemSummaries", [])


def is_valid_item(item):
    condition = (item.get("condition") or "").lower()
    buying_options = item.get("buyingOptions", [])
    seller = item.get("seller", {})
    feedback_percentage = seller.get("feedbackPercentage")

    if "new" not in condition:
        return False

    if "FIXED_PRICE" not in buying_options:
        return False

    if feedback_percentage is None:
        return False

    try:
        if float(feedback_percentage) < MIN_SELLER_FEEDBACK:
            return False
    except ValueError:
        return False

    return True


def import_products(query, category="tech"):
    items = search_ebay_products(query)

    valid_items = [item for item in items if is_valid_item(item)]

    if not valid_items:
        print("Nessun prodotto valido trovato con filtri: nuovo, compralo subito, feedback > 98%.")
        return

    for item in valid_items:
        title = item.get("title")
        price_value = item.get("price", {}).get("value")
        image_url = item.get("image", {}).get("imageUrl")
        product_url = item.get("itemWebUrl")
        condition = item.get("condition")
        buying_options = item.get("buyingOptions", [])
        listing_type = "FIXED_PRICE" if "FIXED_PRICE" in buying_options else None
        seller_feedback = item.get("seller", {}).get("feedbackPercentage")

        if not title or not price_value or not product_url:
            continue

        save_product_offer(
            name=title,
            category=category,
            image_url=image_url,
            store_name=EBAY_STORE_NAME,
            store_website=EBAY_STORE_WEBSITE,
            store_type=EBAY_STORE_TYPE,
            current_price=float(price_value),
            old_price=None,
            product_url=product_url,
            availability="available",
            search_keywords=query,
            condition=condition,
            listing_type=listing_type,
            seller_feedback_percentage=float(seller_feedback)
        )


if __name__ == "__main__":
    import_products("PlayStation 5 Slim", category="gaming")