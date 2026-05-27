import json
import os

import requests


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 5.0


def llm_enabled():
    enabled = os.getenv("SPARIO_ENABLE_LLM_INTENT", "").strip().lower()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return enabled in {"1", "true", "yes", "on"} and bool(api_key)


def llm_model():
    return os.getenv("SPARIO_LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def llm_timeout():
    raw_timeout = os.getenv("SPARIO_LLM_TIMEOUT_SECONDS", "").strip()

    if not raw_timeout:
        return DEFAULT_TIMEOUT_SECONDS

    try:
        timeout = float(raw_timeout)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS

    return max(1.0, min(timeout, 12.0))


def safe_json_loads(value):
    if not value:
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def call_openai_json(messages, schema, max_tokens=350):
    if not llm_enabled():
        return None

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    payload = {
        "model": llm_model(),
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema["name"],
                "strict": True,
                "schema": schema["schema"],
            },
        },
    }

    try:
        response = requests.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=llm_timeout(),
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    choices = data.get("choices") or []
    if not choices:
        return None

    message = choices[0].get("message") or {}
    content = message.get("content")
    return safe_json_loads(content)


def interpret_question_with_llm(question, fallback_payload, allowed_intents, allowed_categories):
    schema = {
        "name": "spario_question_interpretation",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "intent": {"type": "string", "enum": allowed_intents},
                "category": {
                    "anyOf": [
                        {"type": "string", "enum": allowed_categories},
                        {"type": "null"},
                    ]
                },
                "brand": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "budget_max": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "query": {"type": "string"},
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 8,
                },
                "product_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 8,
                },
                "model_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 6,
                },
                "needs": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "wireless",
                            "anc",
                            "sport",
                            "work",
                            "student",
                            "gaming",
                            "tv_ps5",
                            "portable",
                            "cheap",
                        ],
                    },
                    "maxItems": 6,
                },
                "sort_preference": {
                    "type": "string",
                    "enum": [
                        "relevance",
                        "lowest_price",
                        "best_value",
                        "discount",
                        "timing",
                    ],
                },
            },
            "required": [
                "intent",
                "category",
                "brand",
                "budget_max",
                "query",
                "keywords",
                "product_keywords",
                "model_terms",
                "needs",
                "sort_preference",
            ],
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "Sei il parser intenti di Spario, app italiana di shopping intelligence. "
                "Devi solo interpretare la domanda dell'utente in JSON. Non inventare "
                "prodotti, prezzi, disponibilita, sconti o retailer. Se sei incerto, "
                "rimani generico e usa i parametri del fallback. Estrai brand, modello, "
                "keyword prodotto, budget massimo, bisogni e preferenza di ordinamento."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "fallback_rule_based": fallback_payload,
                    "allowed_intents": allowed_intents,
                    "allowed_categories": allowed_categories,
                },
                ensure_ascii=True,
            ),
        },
    ]
    interpreted = call_openai_json(messages, schema=schema, max_tokens=300)

    if not isinstance(interpreted, dict):
        return None

    return interpreted


def generate_shopping_response_with_llm(question, parsed_payload, product_cards):
    schema = {
        "name": "spario_shopping_response",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "answer_title": {"type": "string"},
                "answer_summary": {"type": "string"},
                "ranked_product_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 6,
                },
                "product_reasons": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "product_id": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["product_id", "reason"],
                    },
                    "maxItems": 6,
                },
            },
            "required": [
                "answer_title",
                "answer_summary",
                "ranked_product_ids",
                "product_reasons",
            ],
        },
    }
    safe_cards = product_cards[:12]
    messages = [
        {
            "role": "system",
            "content": (
                "Sei Spario AI Shopping Assistant. Devi scrivere una risposta breve, "
                "premium e pratica in italiano. Puoi usare SOLO i prodotti nel JSON "
                "fornito. Non inventare prodotti, prezzi, sconti, retailer, immagini "
                "o disponibilita. Se i dati sono pochi, dillo con cautela. La risposta "
                "deve essere corta: titolo + una riga. Le card prodotto faranno il resto."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "parsed_question": parsed_payload,
                    "real_supabase_products": safe_cards,
                    "instructions": {
                        "rank_only_existing_product_ids": True,
                        "max_ranked_products": 6,
                        "reason_max_chars": 110,
                    },
                },
                ensure_ascii=True,
            ),
        },
    ]
    response = call_openai_json(messages, schema=schema, max_tokens=420)

    if not isinstance(response, dict):
        return None

    return response
