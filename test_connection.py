from core.supabase_client import get_supabase_client


def main():
    supabase = get_supabase_client()
    response = supabase.table("stores").select("*").execute()
    print(response.data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
