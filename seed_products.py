from supabase import create_client
import uuid
import random

url = "https://bbnjiqfrqafcqbsemhff.supabase.co"

key = "sb_publishable_ZqAmZKzXfQvdWvmTTWnAhg_O4Qcu4qo"

supabase = create_client(url, key)

stores = supabase.table("stores").select("*").execute().data

store_map = {store["name"]: store["id"] for store in stores}

products = [

    # GAMING
    {"name": "PlayStation 5 Slim", "category": "gaming"},
    {"name": "Xbox Series X", "category": "gaming"},
    {"name": "Nintendo Switch OLED", "category": "gaming"},
    {"name": "DualSense PS5 Controller", "category": "gaming"},
    {"name": "Xbox Wireless Controller", "category": "gaming"},
    {"name": "Nintendo Switch Pro Controller", "category": "gaming"},
    {"name": "SteelSeries Arctis Nova 7", "category": "gaming"},
    {"name": "Razer BlackShark V2", "category": "gaming"},
    {"name": "Logitech G Pro X", "category": "gaming"},
    {"name": "ASUS ROG Gaming Monitor 27", "category": "gaming"},
    {"name": "MSI Curved Gaming Monitor", "category": "gaming"},
    {"name": "Secretlab Gaming Chair", "category": "gaming"},
    {"name": "Elgato Stream Deck", "category": "gaming"},
    {"name": "HyperX QuadCast", "category": "gaming"},
    {"name": "Meta Quest 3", "category": "gaming"},

    # TECH
    {"name": "iPhone 16 Pro", "category": "tech"},
    {"name": "iPhone 16", "category": "tech"},
    {"name": "Samsung Galaxy S25", "category": "tech"},
    {"name": "Google Pixel 9", "category": "tech"},
    {"name": "MacBook Air M4", "category": "tech"},
    {"name": "MacBook Pro M4", "category": "tech"},
    {"name": "iPad Pro M4", "category": "tech"},
    {"name": "AirPods Pro 2", "category": "tech"},
    {"name": "Apple Watch Series 10", "category": "tech"},
    {"name": "Samsung Galaxy Watch 7", "category": "tech"},
    {"name": "Sony WH-1000XM5", "category": "tech"},
    {"name": "Bose QuietComfort Ultra", "category": "tech"},
    {"name": "Dyson V15 Detect", "category": "tech"},
    {"name": "LG OLED C4 55", "category": "tech"},
    {"name": "Samsung OLED S95D", "category": "tech"},
    {"name": "GoPro Hero 13", "category": "tech"},
    {"name": "DJI Mini 4 Pro", "category": "tech"},
    {"name": "Kindle Paperwhite", "category": "tech"},
    {"name": "Logitech MX Master 3S", "category": "tech"},
    {"name": "Logitech MX Keys S", "category": "tech"},
    {"name": "Anker Power Bank 20K", "category": "tech"},
    {"name": "Philips Hue Starter Kit", "category": "tech"},
    {"name": "Ring Video Doorbell", "category": "tech"},
    {"name": "TP-Link WiFi 7 Router", "category": "tech"},
    {"name": "Nanoleaf Shapes", "category": "tech"},

]

store_names = list(store_map.keys())

for product in products:

    product_id = str(uuid.uuid4())

    image_url = "https://placehold.co/600x600/png"

    supabase.table("products").insert({
        "id": product_id,
        "name": product["name"],
        "category": product["category"],
        "image_url": image_url
    }).execute()

    selected_stores = random.sample(store_names, k=3)

    base_price = random.randint(50, 2000)

    for store in selected_stores:

        current_price = round(base_price + random.randint(-100, 100), 2)

        old_price = round(current_price + random.randint(20, 200), 2)

        supabase.table("product_offers").insert({
            "product_id": product_id,
            "store_id": store_map[store],
            "current_price": current_price,
            "old_price": old_price,
            "product_url": f"https://www.{store.lower()}.it"
        }).execute()

print("Prodotti e offerte inseriti correttamente.")