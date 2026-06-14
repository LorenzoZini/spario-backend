from core.supabase_client import get_supabase_client


supabase = get_supabase_client()

stores = [
    {"name": "Amazon", "website": "https://www.amazon.it", "type": "tech"},
    {"name": "MediaWorld", "website": "https://www.mediaworld.it", "type": "tech"},
    {"name": "Unieuro", "website": "https://www.unieuro.it", "type": "tech"},
    {"name": "GameStop", "website": "https://www.gamestop.it", "type": "gaming"},
    {"name": "Comet", "website": "https://www.comet.it", "type": "tech"},
    {"name": "Euronics", "website": "https://www.euronics.it", "type": "tech"},
]

response = supabase.table("stores").insert(stores).execute()

print("Store inseriti:")
print(response.data)
