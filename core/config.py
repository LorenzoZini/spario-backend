import os

from dotenv import load_dotenv


load_dotenv()


def _get_env(name, default=None):
    return os.getenv(name, default)


# Supabase
SUPABASE_URL = _get_env("SUPABASE_URL")
SUPABASE_KEY = _get_env("SUPABASE_KEY")

# OpenAI
OPENAI_API_KEY = _get_env("OPENAI_API_KEY")
SPARIO_ENABLE_LLM_INTENT = _get_env("SPARIO_ENABLE_LLM_INTENT", "")
SPARIO_LLM_MODEL = _get_env("SPARIO_LLM_MODEL", "gpt-4o-mini")
SPARIO_LLM_TIMEOUT_SECONDS = _get_env("SPARIO_LLM_TIMEOUT_SECONDS", "5")

# API runtime
CORS_ORIGINS = _get_env("CORS_ORIGINS", "*")
HOST = _get_env("HOST", "0.0.0.0")
PORT = _get_env("PORT", "8000")

# Importer integrations
EBAY_CLIENT_ID = _get_env("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = _get_env("EBAY_CLIENT_SECRET")
FIRECRAWL_API_KEY = _get_env("FIRECRAWL_API_KEY")
AMAZON_API_KEY = _get_env("AMAZON_API_KEY")
GOOGLE_PLACES_API_KEY = _get_env("GOOGLE_PLACES_API_KEY")


def get_openai_api_key():
    return _get_env("OPENAI_API_KEY") or OPENAI_API_KEY


def get_llm_intent_enabled():
    return _get_env("SPARIO_ENABLE_LLM_INTENT", SPARIO_ENABLE_LLM_INTENT)


def get_llm_model():
    return _get_env("SPARIO_LLM_MODEL", SPARIO_LLM_MODEL)


def get_llm_timeout_seconds():
    return _get_env(
        "SPARIO_LLM_TIMEOUT_SECONDS",
        SPARIO_LLM_TIMEOUT_SECONDS,
    )


def require_supabase_settings():
    url = _get_env("SUPABASE_URL") or SUPABASE_URL
    key = _get_env("SUPABASE_KEY") or SUPABASE_KEY
    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", url),
            ("SUPABASE_KEY", key),
        )
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return url, key
