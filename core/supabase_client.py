from functools import lru_cache

from supabase import create_client

from core.config import require_supabase_settings


@lru_cache(maxsize=1)
def get_supabase_client():
    url, key = require_supabase_settings()
    return create_client(url, key)


def clear_supabase_client_cache():
    get_supabase_client.cache_clear()
