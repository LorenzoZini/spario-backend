import re
from supabase import create_client
from importers.config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def canonicalize_product_name(name):
    text = name.lower()

    replacements = {
        "second generation": "2",
        "2nd gen": "2",
        "2ª generazione": "2",
        "seconda generazione": "2",
        "usb-c": "usbc",
        "usb c": "usbc",
        "playstation": "ps",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9àèéìòù\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    filler_words = {
        "apple", "sony", "samsung", "microsoft", "nintendo",
        "nuovo", "new", "originale", "offerta", "promo",
        "spedizione", "gratis", "garanzia", "cuffie",
        "auricolari", "wireless", "bluetooth"
    }

    words = [word for word in text.split() if word not in filler_words]

    return "-".join(words)


def find_or_create_product(name, category, image_url=None, search_keywords=None):
    canonical_key = canonicalize_product_name(search_keywords or name)

    existing = (
        supabase.table("products")
        .select("*")
        .eq("category", category)
        .eq("canonical_key", canonical_key)
        .execute()
        .data
    )

    if existing:
        product = existing[0]

        updates = {
            "search_keywords": search_keywords or name
        }

        if image_url and not product.get("image_url"):
            updates["image_url"] = image_url

        supabase.table("products").update(updates).eq("id", product["id"]).execute()

        return product["id"]

    created = supabase.table("products").insert({
        "name": name,
        "category": category,
        "image_url": image_url,
        "search_keywords": search_keywords or name,
        "canonical_key": canonical_key
    }).execute().data[0]

    return created["id"]


def find_or_create_store(store_name, store_website, store_type):
    existing = (
        supabase.table("stores")
        .select("*")
        .eq("name", store_name)
        .execute()
        .data
    )

    if existing:
        return existing[0]["id"]

    created = supabase.table("stores").insert({
        "name": store_name,
        "website": store_website,
        "type": store_type
    }).execute().data[0]

    return created["id"]


def upsert_offer(
    product_id,
    store_id,
    current_price,
    old_price,
    product_url,
    availability,
    condition=None,
    listing_type=None,
    seller_feedback_percentage=None,
    data_confidence=None
):
    existing = (
        supabase.table("product_offers")
        .select("*")
        .eq("product_id", product_id)
        .eq("store_id", store_id)
        .execute()
        .data
    )

    offer_data = {
        "current_price": current_price,
        "old_price": old_price,
        "product_url": product_url,
        "availability": availability,
        "condition": condition,
        "listing_type": listing_type,
        "seller_feedback_percentage": seller_feedback_percentage,
        "data_confidence": data_confidence,
    }

    if existing:
        offer = existing[0]

        previous_price = (
            float(offer["current_price"])
            if offer.get("current_price") is not None
            else None
        )

        new_price = float(current_price)

        supabase.table("product_offers").update(offer_data).eq("id", offer["id"]).execute()

        if previous_price != new_price:
            supabase.table("price_history").insert({
                "product_id": product_id,
                "store_id": store_id,
                "price": new_price,
                "condition": condition,
                "listing_type": listing_type,
                "seller_feedback_percentage": seller_feedback_percentage,
                "data_confidence": data_confidence,
            }).execute()

        print(f"Aggiornata offerta esistente: {product_id} - €{new_price}")
        return

    supabase.table("product_offers").insert({
        "product_id": product_id,
        "store_id": store_id,
        **offer_data
    }).execute()

    supabase.table("price_history").insert({
        "product_id": product_id,
        "store_id": store_id,
        "price": current_price,
        "condition": condition,
        "listing_type": listing_type,
        "seller_feedback_percentage": seller_feedback_percentage,
        "data_confidence": data_confidence,
    }).execute()

    print(f"Nuova offerta creata: {product_id} - €{current_price}")


def save_product_offer(
    name,
    category,
    image_url,
    store_name,
    store_website,
    store_type,
    current_price,
    old_price,
    product_url,
    availability="available",
    search_keywords=None,
    condition=None,
    listing_type=None,
    seller_feedback_percentage=None,
    data_confidence=None
):
    product_id = find_or_create_product(
        name=name,
        category=category,
        image_url=image_url,
        search_keywords=search_keywords
    )

    store_id = find_or_create_store(
        store_name=store_name,
        store_website=store_website,
        store_type=store_type
    )

    upsert_offer(
        product_id=product_id,
        store_id=store_id,
        current_price=current_price,
        old_price=old_price,
        product_url=product_url,
        availability=availability,
        condition=condition,
        listing_type=listing_type,
        seller_feedback_percentage=seller_feedback_percentage,
        data_confidence=data_confidence
    )

    print(f"Salvato correttamente: {name} - {store_name}")