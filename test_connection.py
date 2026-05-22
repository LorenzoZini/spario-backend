from supabase import create_client

url = "https://bbnjiqfrqafcqbsemhff.supabase.co"

key = "sb_publishable_ZqAmZKzXfQvdWvmTTWnAhg_O4Qcu4qo"

supabase = create_client(url, key)

response = supabase.table("stores").select("*").execute()

print(response.data)
