import argparse
import re
import statistics
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from supabase import create_client

from ai.llm_interpreter import (
    generate_shopping_response_with_llm,
    interpret_question_with_llm,
)
from importers.config import SUPABASE_KEY, SUPABASE_URL
from predictions.price_predictor import predict_offer


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

VALID_CONFIDENCE_VALUES = {"alta", "media"}
DEFAULT_PRODUCT_LIMIT = 5
DEFAULT_HISTORY_MIN_POINTS = 3
DEFAULT_CARD_LIMIT = 6
ALLOWED_INTENTS = [
    "cheapest_offer",
    "best_under_budget",
    "when_to_buy",
    "category_recommendation",
    "discount_ranking",
    "product_search",
    "unknown",
]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


CATEGORY_ALIASES = {
    "tv": [
        "tv",
        "smart tv",
        "televisore",
        "televisori",
        "oled",
        "qled",
    ],
    "cuffie": [
        "cuffie",
        "cuffia",
        "auricolari",
        "auricolare",
        "airpods",
        "earbuds",
        "headphone",
    ],
    "smartphone": [
        "smartphone",
        "telefono",
        "telefoni",
        "cellulare",
        "cellulari",
        "iphone",
        "samsung",
        "galaxy",
        "xiaomi",
        "oppo",
        "motorola",
        "honor",
    ],
    "laptop": [
        "laptop",
        "notebook",
        "portatile",
        "portatili",
        "macbook",
        "ultrabook",
    ],
    "casse_audio": [
        "casse",
        "cassa",
        "speaker",
        "altoparlanti",
        "altoparlante",
        "bluetooth",
        "jbl",
    ],
    "desktop": [
        "desktop",
        "pc fisso",
        "computer fisso",
        "all in one",
        "aio",
    ],
    "gaming": [
        "gaming",
        "ps5",
        "playstation",
        "xbox",
        "nintendo",
        "switch",
    ],
}

CATEGORY_FALLBACKS = {
    "gaming": ["tech", "gaming"],
}

BRAND_ALIASES = {
    "apple": ["apple", "airpods", "iphone", "ipad", "macbook"],
    "samsung": ["samsung", "galaxy"],
    "sony": ["sony", "playstation", "ps5"],
    "microsoft": ["microsoft", "xbox"],
    "nintendo": ["nintendo", "switch"],
    "xiaomi": ["xiaomi", "redmi", "poco"],
    "oppo": ["oppo"],
    "motorola": ["motorola", "moto"],
    "honor": ["honor"],
    "jbl": ["jbl"],
    "lg": ["lg"],
    "hp": ["hp"],
    "lenovo": ["lenovo"],
    "asus": ["asus"],
    "acer": ["acer"],
}

SYNONYM_TERMS = {
    "ps5": ["ps5", "playstation", "playstation 5"],
    "playstation": ["ps5", "playstation", "playstation 5"],
    "airpods": ["airpods", "auricolari", "cuffie"],
    "iphone": ["iphone", "apple"],
    "galaxy": ["galaxy", "samsung"],
    "tv": ["tv", "televisore", "smart tv"],
    "televisore": ["tv", "televisore", "smart tv"],
    "cuffie": ["cuffie", "auricolari", "headphone"],
    "auricolari": ["cuffie", "auricolari", "earbuds"],
    "laptop": ["laptop", "notebook", "portatile"],
    "notebook": ["laptop", "notebook", "portatile"],
    "portatile": ["laptop", "notebook", "portatile"],
    "casse": ["casse", "speaker", "altoparlanti"],
    "speaker": ["casse", "speaker", "altoparlanti"],
}

PRODUCT_BRAND_TOKENS = {
    "airpods",
    "apple",
    "iphone",
    "ipad",
    "macbook",
    "playstation",
    "ps5",
    "xbox",
    "nintendo",
    "switch",
    "galaxy",
    "samsung",
    "xiaomi",
    "oppo",
    "motorola",
    "honor",
    "sony",
    "jbl",
    "lg",
    "hp",
    "lenovo",
    "asus",
    "acer",
    "redmi",
    "poco",
}

SINGLE_TOKEN_PRODUCT_QUERIES = {
    "airpods",
    "iphone",
    "ipad",
    "macbook",
    "ps5",
    "playstation",
    "xbox",
    "nintendo",
}

PRODUCT_SPECIFIC_PHRASES = {
    "airpods max",
    "airpods pro",
    "iphone 15",
    "iphone 16",
    "iphone 15 pro",
    "iphone 16 pro",
    "lg oled",
    "jbl speaker",
    "jbl bluetooth",
    "playstation 5",
    "samsung galaxy",
}

MODEL_TOKENS = {
    "max",
    "pro",
    "mini",
    "plus",
    "ultra",
    "oled",
    "qled",
    "qnED".lower(),
    "ps5",
    "m1",
    "m2",
    "m3",
    "m4",
    "15",
    "16",
}

NEED_ALIASES = {
    "wireless": ["wireless", "bluetooth", "senza fili", "tws"],
    "anc": ["anc", "cancellazione rumore", "noise cancelling"],
    "sport": ["palestra", "sport", "corsa", "allenamento", "impermeabile"],
    "work": ["lavoro", "ufficio", "produttivita", "smart working"],
    "student": ["universita", "studio", "scuola", "studenti"],
    "gaming": ["gaming", "ps5", "playstation", "xbox", "nintendo"],
    "tv_ps5": ["tv per ps5", "televisore per ps5", "hdmi 2 1", "120hz"],
    "portable": ["portatile", "leggero", "mobilita"],
    "cheap": ["economico", "economica", "economici", "economiche", "budget"],
}

SORT_PREFERENCES = {
    "discount": ["sconto", "scontato", "scontata", "ribasso", "risparmio"],
    "lowest_price": ["costa meno", "prezzo basso", "piu economico", "economico", "sotto", "budget"],
    "best_value": ["miglior", "migliore", "migliori", "buono", "buona", "consigli", "consiglia"],
    "timing": ["quando", "conviene", "aspettare", "previsione"],
}

GENERIC_PRODUCT_TOKENS = {
    "bluetooth",
    "wireless",
    "cuffie",
    "cuffia",
    "auricolari",
    "auricolare",
    "smartphone",
    "telefono",
    "cellulare",
    "tv",
    "smart",
    "televisore",
    "laptop",
    "notebook",
    "portatile",
    "casse",
    "speaker",
    "audio",
}

CATEGORY_ALIAS_BLOCKLIST = PRODUCT_BRAND_TOKENS | {
    "bluetooth",
    "wireless",
    "smart",
    "gaming",
    "ps5",
    "playstation",
    "xbox",
    "nintendo",
    "switch",
    "airpods",
    "iphone",
}

STOPWORDS = {
    "a",
    "ad",
    "al",
    "alla",
    "allo",
    "anche",
    "che",
    "chi",
    "cosa",
    "costa",
    "costano",
    "costi",
    "comprare",
    "conviene",
    "con",
    "da",
    "del",
    "della",
    "delle",
    "di",
    "dove",
    "economiche",
    "economici",
    "economico",
    "entro",
    "euro",
    "gli",
    "ha",
    "i",
    "il",
    "in",
    "la",
    "le",
    "lo",
    "massimo",
    "meno",
    "miglior",
    "migliore",
    "migliori",
    "offerta",
    "offerte",
    "per",
    "piu",
    "prezzo",
    "prodotto",
    "prodotti",
    "quale",
    "quando",
    "sotto",
    "su",
    "tech",
    "un",
    "una",
}


@dataclass
class ParsedQuestion:
    intent: str
    query: str
    normalized_question: str
    category: str | None = None
    budget: float | None = None
    keywords: tuple[str, ...] = ()
    brand: str | None = None
    product_keywords: tuple[str, ...] = ()
    model_terms: tuple[str, ...] = ()
    needs: tuple[str, ...] = ()
    sort_preference: str = "relevance"


def strip_accents(value):
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_text(value):
    value = strip_accents(str(value or "")).lower()
    value = value.replace("€", " euro ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def parse_price(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_price(value):
    price = parse_price(value)

    if price is None:
        return "prezzo non disponibile"

    return f"€{price:.2f}"


def parse_datetime(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)

    text = str(value).replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed


def fetch_all(table_name, columns):
    rows = []
    page_size = 1000
    start = 0

    while True:
        response = (
            supabase.table(table_name)
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
        supabase.table("product_offers")
        .select(OFFER_COLUMNS)
        .eq("product_id", product_id)
        .execute()
    )
    return response.data or []


def fetch_history_for_product(product_id):
    response = (
        supabase.table("price_history")
        .select(HISTORY_COLUMNS)
        .eq("product_id", product_id)
        .execute()
    )
    return response.data or []


def detect_category(normalized_question):
    best_category = None
    best_score = 0

    for category, aliases in CATEGORY_ALIASES.items():
        score = 0

        for alias in aliases:
            alias_normalized = normalize_text(alias)
            if f" {alias_normalized} " in f" {normalized_question} ":
                score += 3 if " " in alias_normalized else 2

        if score > best_score:
            best_score = score
            best_category = category

    return best_category


def detect_budget(normalized_question):
    patterns = [
        r"(?:sotto|massimo|entro|budget)\s+(?:i\s+)?(\d{2,5})",
        r"meno\s+di\s+(\d{2,5})",
        r"(\d{2,5})\s*(?:euro|eur)",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized_question)
        if not match:
            continue

        price = parse_price(match.group(1))
        if price is not None:
            return price

    return None


def detect_brand(normalized_question):
    best_brand = None
    best_score = 0

    for brand, aliases in BRAND_ALIASES.items():
        score = 0
        for alias in aliases:
            alias_normalized = normalize_text(alias)
            if f" {alias_normalized} " in f" {normalized_question} ":
                score += 3 if " " in alias_normalized else 2

        if score > best_score:
            best_brand = brand
            best_score = score

    return best_brand


def detect_needs(normalized_question):
    needs = []

    for need, aliases in NEED_ALIASES.items():
        for alias in aliases:
            alias_normalized = normalize_text(alias)
            if f" {alias_normalized} " in f" {normalized_question} ":
                needs.append(need)
                break

    return tuple(needs)


def detect_sort_preference(normalized_question, intent):
    for preference, aliases in SORT_PREFERENCES.items():
        if any(alias in normalized_question for alias in aliases):
            return preference

    if intent == "discount_ranking":
        return "discount"

    if intent in {"cheapest_offer", "best_under_budget"}:
        return "lowest_price"

    if intent == "when_to_buy":
        return "timing"

    return "relevance"


def useful_keywords(normalized_question):
    tokens = normalized_question.split()
    keywords = []

    for token in tokens:
        if token in STOPWORDS:
            continue

        if token.isdigit():
            continue

        if len(token) < 2:
            continue

        if token not in keywords:
            keywords.append(token)

    return keywords


def detect_model_terms(keywords):
    terms = []

    for keyword in keywords:
        if keyword in MODEL_TOKENS or re.search(r"\d", keyword):
            if keyword not in terms:
                terms.append(keyword)

    return tuple(terms)


def detect_product_keywords(keywords, brand=None, category=None, needs=()):
    product_keywords = []
    generic_need_terms = set()

    for need in needs:
        for alias in NEED_ALIASES.get(need, []):
            for alias_token in normalize_text(alias).split():
                generic_need_terms.add(alias_token)

    for keyword in keywords:
        if keyword in STOPWORDS:
            continue

        if keyword in generic_need_terms and keyword not in PRODUCT_BRAND_TOKENS:
            continue

        if keyword in GENERIC_PRODUCT_TOKENS and keyword not in MODEL_TOKENS:
            continue

        if keyword not in product_keywords:
            product_keywords.append(keyword)

    return tuple(product_keywords[:8])


def extract_query(normalized_question):
    keywords = useful_keywords(normalized_question)
    return " ".join(keywords)


def detect_intent(normalized_question, category, budget, keywords):
    discount_tokens = ["sconto", "scontato", "scontata", "risparmio", "ribasso"]
    cheapest_tokens = [
        "costa meno",
        "dove costa",
        "prezzo piu basso",
        "prezzo migliore",
        "miglior prezzo",
        "miglior offerta",
        "migliore offerta",
        "meno caro",
        "piu economico",
    ]
    when_tokens = [
        "quando",
        "conviene comprare",
        "comprare ora",
        "aspettare",
        "aspetto",
        "previsione",
        "prezzo scende",
        "prezzo scendera",
    ]
    recommendation_tokens = [
        "migliori",
        "miglior",
        "buono",
        "buona",
        "consigli",
        "consiglia",
        "cerco",
        "lavoro",
        "economiche",
        "economici",
    ]
    search_tokens = ["cerca", "trova", "mostrami", "offerte", "prodotti"]

    if any(token in normalized_question for token in discount_tokens):
        return "discount_ranking"

    if any(token in normalized_question for token in when_tokens):
        return "when_to_buy"

    if any(token in normalized_question for token in cheapest_tokens):
        return "cheapest_offer"

    if budget is not None:
        return "best_under_budget"

    if category and any(token in normalized_question for token in recommendation_tokens):
        return "category_recommendation"

    if any(token in normalized_question for token in search_tokens):
        return "product_search"

    if category and not keywords:
        return "category_recommendation"

    if keywords or category:
        return "product_search"

    return "unknown"


def parsed_question_payload(parsed):
    return {
        "intent": parsed.intent,
        "category": parsed.category,
        "brand": parsed.brand,
        "budget_max": parsed.budget,
        "query": parsed.query,
        "keywords": list(parsed.keywords),
        "product_keywords": list(parsed.product_keywords),
        "model_terms": list(parsed.model_terms),
        "needs": list(parsed.needs),
        "sort_preference": parsed.sort_preference,
    }


def clean_llm_keywords(value):
    if not isinstance(value, list):
        return ()

    keywords = []
    for item in value:
        normalized = normalize_text(item)
        if not normalized:
            continue

        for keyword in useful_keywords(normalized):
            if keyword not in keywords:
                keywords.append(keyword)

    return tuple(keywords[:8])


def parsed_question_from_llm(question, fallback, interpreted):
    if not isinstance(interpreted, dict):
        return fallback

    intent = interpreted.get("intent")
    if intent not in ALLOWED_INTENTS:
        intent = fallback.intent

    category = interpreted.get("category")
    if category not in CATEGORY_ALIASES:
        category = fallback.category

    budget = parse_price(interpreted.get("budget_max", interpreted.get("budget")))
    if budget is None:
        budget = fallback.budget
    elif budget <= 0 or budget > 50000:
        budget = fallback.budget

    query = normalize_text(interpreted.get("query"))
    if not query:
        query = fallback.query

    keywords = clean_llm_keywords(interpreted.get("keywords"))
    if not keywords and query:
        keywords = tuple(useful_keywords(query))
    if not keywords:
        keywords = fallback.keywords

    brand = interpreted.get("brand")
    if brand not in BRAND_ALIASES:
        brand = fallback.brand

    product_keywords = clean_llm_keywords(interpreted.get("product_keywords"))
    if not product_keywords:
        product_keywords = fallback.product_keywords

    model_terms = clean_llm_keywords(interpreted.get("model_terms"))
    if not model_terms:
        model_terms = fallback.model_terms

    needs = interpreted.get("needs")
    if isinstance(needs, list):
        needs = tuple(
            need
            for need in needs[:8]
            if isinstance(need, str) and need in NEED_ALIASES
        )
    else:
        needs = ()
    if not needs:
        needs = fallback.needs

    sort_preference = interpreted.get("sort_preference")
    if sort_preference not in {"relevance", "lowest_price", "best_value", "discount", "timing"}:
        sort_preference = fallback.sort_preference

    normalized = normalize_text(question)
    return ParsedQuestion(
        intent=intent,
        query=query,
        normalized_question=normalized,
        category=category,
        budget=budget,
        keywords=keywords,
        brand=brand,
        product_keywords=product_keywords,
        model_terms=model_terms,
        needs=needs,
        sort_preference=sort_preference,
    )


def parse_question_rule_based(question):
    normalized = normalize_text(question)
    category = detect_category(normalized)
    budget = detect_budget(normalized)
    keywords = tuple(useful_keywords(normalized))
    query = extract_query(normalized)
    intent = detect_intent(normalized, category, budget, keywords)
    brand = detect_brand(normalized)
    needs = detect_needs(normalized)

    if category == "tv" and brand == "sony" and "sony" not in keywords:
        brand = None

    model_terms = detect_model_terms(keywords)
    product_keywords = detect_product_keywords(
        keywords,
        brand=brand,
        category=category,
        needs=needs,
    )
    sort_preference = detect_sort_preference(normalized, intent)

    return ParsedQuestion(
        intent=intent,
        query=query,
        normalized_question=normalized,
        category=category,
        budget=budget,
        keywords=keywords,
        brand=brand,
        product_keywords=product_keywords,
        model_terms=model_terms,
        needs=needs,
        sort_preference=sort_preference,
    )


def parse_question(question):
    fallback = parse_question_rule_based(question)
    interpreted = interpret_question_with_llm(
        question=question,
        fallback_payload=parsed_question_payload(fallback),
        allowed_intents=ALLOWED_INTENTS,
        allowed_categories=list(CATEGORY_ALIASES.keys()),
    )

    return parsed_question_from_llm(question, fallback, interpreted)


def category_values_for_search(category):
    if not category:
        return []

    return [category, *CATEGORY_FALLBACKS.get(category, [])]


def product_search_blob(product):
    return normalize_text(
        " ".join(
            [
                product.get("name") or "",
                product.get("search_keywords") or "",
                product.get("category") or "",
            ]
        )
    )


def text_contains_term(text, term):
    term = normalize_text(term)
    if not term:
        return False

    if " " in term:
        return term in text

    return f" {term} " in f" {text} "


def product_search_tokens(product):
    return set(product_search_blob(product).split())


def query_product_tokens(query, keywords=None):
    normalized = normalize_text(
        " ".join([query or "", " ".join(keywords or [])])
    )
    tokens = []

    for token in normalized.split():
        if token in STOPWORDS:
            continue

        if len(token) < 2 and not token.isdigit():
            continue

        if token not in tokens:
            tokens.append(token)

    return tokens


def looks_product_specific(query, keywords=None):
    tokens = query_product_tokens(query, keywords)
    if not tokens:
        return False

    normalized = normalize_text(" ".join([query or "", " ".join(keywords or [])]))
    if any(phrase in normalized for phrase in PRODUCT_SPECIFIC_PHRASES):
        return True

    if any(token in SINGLE_TOKEN_PRODUCT_QUERIES for token in tokens):
        return True

    has_brand = any(token in PRODUCT_BRAND_TOKENS for token in tokens)
    non_generic_tokens = [
        token
        for token in tokens
        if token not in PRODUCT_BRAND_TOKENS and token not in GENERIC_PRODUCT_TOKENS
    ]

    return has_brand and bool(non_generic_tokens)


def exact_product_match_score(product, query, keywords=None):
    tokens = query_product_tokens(query, keywords)
    if not tokens or not looks_product_specific(query, keywords):
        return 0

    blob = product_search_blob(product)
    blob_tokens = product_search_tokens(product)

    required_tokens = [
        token
        for token in tokens
        if token not in GENERIC_PRODUCT_TOKENS
    ]

    if not required_tokens:
        required_tokens = tokens

    if not all(token in blob_tokens for token in required_tokens):
        return 0

    score = 1000 + (len(required_tokens) * 100)
    exact_phrase = " ".join(required_tokens)

    if exact_phrase and exact_phrase in blob:
        score += 500

    product_name = normalize_text(product.get("name"))
    if exact_phrase and exact_phrase in product_name:
        score += 300

    if product_name.startswith(exact_phrase):
        score += 150

    return score


def parsed_search_tokens(parsed):
    tokens = []

    for source in (
        parsed.product_keywords,
        parsed.model_terms,
        parsed.keywords,
        parsed.needs,
    ):
        for token in source:
            for normalized in normalize_text(token).split():
                if normalized in STOPWORDS:
                    continue

                if normalized not in tokens:
                    tokens.append(normalized)

    return tokens


def product_specific_required_tokens(parsed):
    tokens = []

    for token in parsed_search_tokens(parsed):
        if token in GENERIC_PRODUCT_TOKENS and token not in MODEL_TOKENS:
            continue

        if token in NEED_ALIASES:
            continue

        if token not in tokens:
            tokens.append(token)

    return tokens


def brand_matches_product(product, brand):
    if not brand:
        return True

    blob = product_search_blob(product)
    return any(
        normalize_text(alias) in blob
        for alias in BRAND_ALIASES.get(brand, [brand])
    )


def need_matches_product(product, need):
    blob = product_search_blob(product)

    if need == "cheap":
        return True

    return any(
        normalize_text(alias) in blob
        for alias in NEED_ALIASES.get(need, [])
    )


def looks_product_specific_parsed(parsed):
    if parsed.category == "tv" and "tv_ps5" in parsed.needs:
        return False

    if looks_product_specific(parsed.query, parsed.product_keywords or parsed.keywords):
        return True

    if parsed.model_terms and (parsed.brand or parsed.product_keywords):
        return True

    required_tokens = product_specific_required_tokens(parsed)
    return len(required_tokens) >= 2 and bool(parsed.brand)


def hybrid_product_score(product, parsed):
    blob = product_search_blob(product)
    blob_tokens = product_search_tokens(product)
    product_name = normalize_text(product.get("name"))
    score = 0.0

    if parsed.category and not category_matches(product, parsed.category):
        return 0

    exact_score = exact_product_match_score(
        product,
        parsed.query,
        keywords=parsed.product_keywords or parsed.keywords,
    )
    if exact_score:
        score += exact_score

    if parsed.category:
        score += 90

    if parsed.brand:
        if brand_matches_product(product, parsed.brand):
            score += 130
        elif looks_product_specific_parsed(parsed):
            return 0

    required_tokens = product_specific_required_tokens(parsed)
    if looks_product_specific_parsed(parsed) and required_tokens:
        if not all(token in blob_tokens for token in required_tokens):
            return 0
        score += 120 * len(required_tokens)

    search_tokens = parsed_search_tokens(parsed)
    matched_tokens = []
    for token in search_tokens:
        if token in blob_tokens:
            matched_tokens.append(token)
            if token in parsed.model_terms:
                score += 85
            elif token in parsed.product_keywords:
                score += 70
            elif token in parsed.needs:
                score += 45
            else:
                score += 35
        elif token in blob:
            matched_tokens.append(token)
            score += 18

    phrase = " ".join(
        token
        for token in parsed.product_keywords
        if token not in GENERIC_PRODUCT_TOKENS
    )
    if phrase and phrase in product_name:
        score += 180
    elif parsed.query and normalize_text(parsed.query) in product_name:
        score += 120

    for need in parsed.needs:
        if need_matches_product(product, need):
            score += 55

    if parsed.keywords and not matched_tokens and not parsed.category and not parsed.brand:
        return 0

    return score


def retrieve_products(parsed, limit=80):
    products = fetch_products()
    scored = []

    for product in products:
        score = hybrid_product_score(product, parsed)
        if score <= 0:
            continue

        scored.append((score, product))

    if parsed.brand:
        brand_scored = [
            item
            for item in scored
            if brand_matches_product(item[1], parsed.brand)
        ]
        if brand_scored:
            scored = brand_scored

    if not scored and looks_product_specific_parsed(parsed):
        return []

    if not scored and parsed.category:
        for product in products:
            if category_matches(product, parsed.category):
                scored.append((20, product))

    if not scored and parsed.budget is not None:
        scored = [(1, product) for product in products]

    scored.sort(key=lambda item: (-item[0], product_search_blob(item[1])))
    return [product for _, product in scored[:limit]]


def expanded_terms(keywords, category=None):
    terms = set()

    for keyword in keywords:
        normalized = normalize_text(keyword)
        if not normalized:
            continue

        terms.add(normalized)

        for synonym in SYNONYM_TERMS.get(normalized, []):
            terms.add(normalize_text(synonym))

    if category and not keywords:
        for alias in CATEGORY_ALIASES.get(category, []):
            terms.add(normalize_text(alias))

    return [term for term in terms if term]


def category_matches(product, category):
    if not category:
        return True

    product_category = normalize_text(product.get("category"))
    search_values = category_values_for_search(category)

    if product_category in search_values:
        return True

    blob = product_search_blob(product)
    return any(
        text_contains_term(blob, alias)
        for alias in CATEGORY_ALIASES.get(category, [])
        if normalize_text(alias) not in CATEGORY_ALIAS_BLOCKLIST
    )


def score_product(product, query, category=None, keywords=None):
    blob = product_search_blob(product)
    keywords = list(keywords or useful_keywords(normalize_text(query)))

    if category and not category_matches(product, category):
        return 0

    score = 0

    if category and category_matches(product, category):
        score += 20

    terms = expanded_terms(keywords, category=category)

    meaningful_terms = [
        term
        for term in terms
        if len(term) >= 2 and not term.isdigit() and term not in STOPWORDS
    ]

    if meaningful_terms:
        matched_any = False
        for term in meaningful_terms:
            if term in blob:
                matched_any = True
                score += 12 if " " in term else 5

        important_keywords = [
            keyword
            for keyword in keywords
            if keyword not in STOPWORDS and not keyword.isdigit()
        ]

        if important_keywords:
            matched_important = any(keyword in blob for keyword in important_keywords)
            if not matched_important:
                return 0

        if not matched_any:
            return 0

    product_category = normalize_text(product.get("category"))
    if category and product_category == category:
        score += 10

    return score


def search_products(query, limit=DEFAULT_PRODUCT_LIMIT, category=None, keywords=None):
    normalized_query = normalize_text(query)
    keywords = tuple(keywords or useful_keywords(normalized_query))
    brand = detect_brand(normalized_query)
    needs = detect_needs(normalized_query)
    parsed = ParsedQuestion(
        intent="product_search",
        query=normalized_query,
        normalized_question=normalized_query,
        category=category,
        budget=None,
        keywords=keywords,
        brand=brand,
        product_keywords=detect_product_keywords(
            keywords,
            brand=brand,
            category=category,
            needs=needs,
        ),
        model_terms=detect_model_terms(keywords),
        needs=needs,
        sort_preference="relevance",
    )
    return retrieve_products(parsed, limit=limit)


def is_offer_usable(offer):
    price = parse_price(offer.get("current_price"))
    if price is None:
        return False

    availability = normalize_text(offer.get("availability"))
    if availability in {"out_of_stock", "non disponibile", "esaurito"}:
        return False

    confidence = offer.get("data_confidence")
    if confidence and confidence not in VALID_CONFIDENCE_VALUES:
        return False

    condition = offer.get("condition")
    if condition and condition != "new":
        return False

    return True


def store_lookup():
    return {store.get("id"): store for store in fetch_stores()}


def get_best_offer(product_id, stores_by_id=None):
    offers = fetch_offers_for_product(product_id)
    stores_by_id = stores_by_id or store_lookup()
    usable_offers = []

    for offer in offers:
        if not is_offer_usable(offer):
            continue

        store = stores_by_id.get(offer.get("store_id"), {})
        usable_offers.append({
            "offer": offer,
            "store": store,
            "price": parse_price(offer.get("current_price")),
        })

    if not usable_offers:
        return None

    usable_offers.sort(key=lambda item: item["price"])
    best = usable_offers[0]

    return {
        "product_id": product_id,
        "store_id": best["offer"].get("store_id"),
        "store_name": best["store"].get("name") or "Store sconosciuto",
        "store_website": best["store"].get("website"),
        "price": best["price"],
        "old_price": parse_price(best["offer"].get("old_price")),
        "product_url": best["offer"].get("product_url"),
        "availability": best["offer"].get("availability"),
        "data_confidence": best["offer"].get("data_confidence"),
        "offers_checked": len(usable_offers),
    }


def offer_record(product, best_offer):
    if not best_offer:
        return None

    old_price = parse_price(best_offer.get("old_price"))
    price = parse_price(best_offer.get("price"))
    discount_pct = None

    if old_price and price and old_price > price:
        discount_pct = ((old_price - price) / old_price) * 100

    return {
        "product": product,
        "offer": best_offer,
        "price": price,
        "old_price": old_price,
        "discount_pct": discount_pct,
    }


def product_card_from_record(record, reason=None):
    product = record["product"]
    offer = record["offer"]

    if reason is None:
        reasons = []

        if record.get("discount_pct"):
            reasons.append(f"sconto reale {record['discount_pct']:.1f}%")

        confidence = offer.get("data_confidence")
        if confidence:
            reasons.append(f"dato {confidence}")

        if not reasons:
            reasons.append("prezzo piu basso tra i dati disponibili")

        reason = ", ".join(reasons)

    return {
        "product_id": product.get("id"),
        "name": product.get("name"),
        "category": product.get("category"),
        "image_url": product.get("image_url"),
        "store_name": offer.get("store_name"),
        "price": record.get("price"),
        "old_price": record.get("old_price"),
        "discount_pct": record.get("discount_pct"),
        "product_url": offer.get("product_url"),
        "availability": offer.get("availability"),
        "data_confidence": offer.get("data_confidence"),
        "reason": reason,
    }


def product_cards_from_records(records, limit=DEFAULT_CARD_LIMIT, reasons_by_product_id=None):
    reasons_by_product_id = reasons_by_product_id or {}
    cards = []

    for record in records:
        if len(cards) >= limit:
            break

        if not record.get("product") or not record.get("offer"):
            continue

        product_id = record["product"].get("id")
        reason = reasons_by_product_id.get(product_id)
        cards.append(product_card_from_record(record, reason=reason))

    return cards


def collect_offer_records(products, budget=None):
    records = []
    stores_by_id = store_lookup()

    for product in products:
        record = offer_record(
            product,
            get_best_offer(product.get("id"), stores_by_id=stores_by_id),
        )
        if not record:
            continue

        if budget is not None and record["price"] > budget:
            continue

        records.append(record)

    return records


def confidence_score(value):
    if value == "alta":
        return 20

    if value == "media":
        return 10

    return 0


def price_component(price, min_price, max_price):
    if price is None:
        return 0

    if max_price <= min_price:
        return 35

    return ((max_price - price) / (max_price - min_price)) * 70


def record_hybrid_score(record, parsed, min_price, max_price):
    product = record["product"]
    offer = record["offer"]
    score = hybrid_product_score(product, parsed)
    price = record.get("price")

    if parsed.sort_preference in {"lowest_price", "discount"}:
        score += price_component(price, min_price, max_price)
    else:
        score += price_component(price, min_price, max_price) * 0.35

    if parsed.budget is not None and price is not None:
        if price <= parsed.budget:
            score += 50
            score += max(0, 25 - ((parsed.budget - price) / max(parsed.budget, 1)) * 20)
        else:
            score -= 250

    discount_pct = record.get("discount_pct") or 0
    if parsed.sort_preference == "discount" or parsed.intent == "discount_ranking":
        score += min(160, discount_pct * 2.5)
    else:
        score += min(65, discount_pct * 1.2)

    score += confidence_score(offer.get("data_confidence"))
    score += min(25, (offer.get("offers_checked") or 1) * 5)

    if normalize_text(offer.get("availability")) == "available":
        score += 15

    if parsed.intent == "when_to_buy":
        score += 20

    return score


def similar_product_key(name):
    color_tokens = {
        "nero",
        "nera",
        "bianco",
        "bianca",
        "blu",
        "rosso",
        "rossa",
        "verde",
        "argento",
        "silver",
        "grigio",
        "grigia",
        "arancione",
        "rosa",
        "yellow",
        "black",
        "white",
    }
    tokens = [
        token
        for token in normalize_text(name).split()
        if token not in color_tokens and token not in STOPWORDS
    ]
    return " ".join(tokens[:10])


def dedupe_similar_records(records, parsed):
    if looks_product_specific_parsed(parsed):
        return records

    deduped = []
    seen_ids = set()
    seen_names = set()

    for record in records:
        product = record["product"]
        product_id = product.get("id")
        name_key = similar_product_key(product.get("name"))

        if product_id in seen_ids or name_key in seen_names:
            continue

        deduped.append(record)
        seen_ids.add(product_id)
        seen_names.add(name_key)

    return deduped


def rank_offer_records(records, parsed):
    if not records:
        return []

    prices = [
        record.get("price")
        for record in records
        if record.get("price") is not None
    ]
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else min_price

    for record in records:
        record["ranking_score"] = record_hybrid_score(
            record,
            parsed,
            min_price=min_price,
            max_price=max_price,
        )

    records.sort(
        key=lambda item: (
            -item.get("ranking_score", 0),
            item.get("price") if item.get("price") is not None else float("inf"),
            product_search_blob(item["product"]),
        )
    )
    return dedupe_similar_records(records, parsed)


def products_and_records_for_parsed(parsed):
    if parsed.intent == "unknown":
        return [], []

    if parsed.intent == "discount_ranking":
        products = retrieve_products(parsed, limit=160)

        if not products:
            products = fetch_products()

        records = [
            record
            for record in collect_offer_records(products)
            if record["discount_pct"] is not None and record["discount_pct"] > 0
        ]
        records = rank_offer_records(records, parsed)
        return products, records

    if parsed.intent == "best_under_budget":
        limit = 300 if not parsed.category and not parsed.keywords else 160
        products = retrieve_products(parsed, limit=limit)
        records = collect_offer_records(products, budget=parsed.budget)
        records = rank_offer_records(records, parsed)
        return products, records

    product_limit = 40 if parsed.intent in {"cheapest_offer", "category_recommendation"} else DEFAULT_PRODUCT_LIMIT
    if looks_product_specific_parsed(parsed):
        product_limit = max(product_limit, 20)

    products = retrieve_products(parsed, limit=product_limit)

    if not products:
        return [], []

    if parsed.intent == "when_to_buy":
        record = offer_record(products[0], get_best_offer(products[0].get("id")))
        return products, [record] if record else []

    records = collect_offer_records(products, budget=parsed.budget)
    records = rank_offer_records(records, parsed)
    return products, records


def is_history_usable(row):
    price = parse_price(row.get("price"))
    if price is None:
        return False

    confidence = row.get("data_confidence")
    if confidence and confidence not in VALID_CONFIDENCE_VALUES:
        return False

    condition = row.get("condition")
    if condition and condition != "new":
        return False

    listing_type = row.get("listing_type")
    if listing_type and listing_type != "retail_online":
        return False

    return True


def get_price_context(product_id):
    history = [
        row
        for row in fetch_history_for_product(product_id)
        if is_history_usable(row)
    ]
    history.sort(key=lambda row: parse_datetime(row.get("checked_at")))

    prices = [parse_price(row.get("price")) for row in history]
    prices = [price for price in prices if price is not None]

    if not prices:
        return {
            "product_id": product_id,
            "history_points": 0,
            "min_price": None,
            "max_price": None,
            "avg_price": None,
            "latest_price": None,
        }

    return {
        "product_id": product_id,
        "history_points": len(prices),
        "min_price": min(prices),
        "max_price": max(prices),
        "avg_price": statistics.mean(prices),
        "latest_price": prices[-1],
    }


def get_prediction_for_product(product, best_offer):
    if not best_offer:
        return None

    history_rows = [
        row
        for row in fetch_history_for_product(product.get("id"))
        if row.get("store_id") == best_offer.get("store_id") and is_history_usable(row)
    ]
    history_rows.sort(key=lambda row: parse_datetime(row.get("checked_at")))

    offer = {
        "store_id": best_offer.get("store_id"),
        "current_price": best_offer.get("price"),
        "availability": best_offer.get("availability") or "available",
    }

    prediction = predict_offer(
        product=product,
        offer=offer,
        store_name=best_offer.get("store_name") or "Store sconosciuto",
        history_rows=history_rows,
        min_history_points=DEFAULT_HISTORY_MIN_POINTS,
    )

    if prediction.recommendation == "insufficient_data":
        return None

    return prediction


def product_label(product):
    return product.get("name") or "Prodotto senza nome"


def category_label(category):
    labels = {
        "tv": "TV",
        "cuffie": "cuffie",
        "smartphone": "smartphone",
        "laptop": "laptop",
        "casse_audio": "casse audio",
        "desktop": "desktop",
        "gaming": "prodotti gaming",
    }
    return labels.get(category, "prodotti")


def display_product_token(token):
    labels = {
        "airpods": "AirPods",
        "iphone": "iPhone",
        "ipad": "iPad",
        "macbook": "MacBook",
        "ps5": "PS5",
        "playstation": "PlayStation",
        "xbox": "Xbox",
        "nintendo": "Nintendo",
    }
    return labels.get(token, token.upper() if token.isdigit() else token.capitalize())


def product_specific_query_label(parsed):
    tokens = [
        token
        for token in query_product_tokens(parsed.query, parsed.keywords)
        if token not in GENERIC_PRODUCT_TOKENS
    ]

    if not tokens:
        tokens = query_product_tokens(parsed.query, parsed.keywords)

    return " ".join(display_product_token(token) for token in tokens[:4])


def answer_product_specific_match(parsed, records):
    if not records:
        return "Ho trovato questo prodotto tra quelli tracciati, ma non ho offerte valide al momento."

    if len(records) == 1:
        return "Ho trovato questo prodotto tra quelli tracciati."

    return "Ho trovato questi prodotti tra quelli tracciati."


def short_answer_for_results(parsed, products, records, original_question):
    if not products:
        return no_products_response(parsed, original_question)

    if looks_product_specific_parsed(parsed):
        return answer_product_specific_match(parsed, records)

    if not records:
        return (
            "Ho trovato prodotti coerenti, ma non offerte valide al momento.\n"
            f"{followup_text()}"
        )

    if parsed.intent == "discount_ranking" or parsed.sort_preference == "discount":
        return "Migliori sconti reali trovati.\nLe card mostrano solo offerte con sconto calcolabile."

    if parsed.intent == "when_to_buy":
        return answer_when_to_buy(parsed, products)

    if parsed.budget is not None:
        return (
            f"Ho trovato {min(len(records), DEFAULT_CARD_LIMIT)} opzioni sotto "
            f"{format_price(parsed.budget)}.\n"
            "Le card sono ordinate per rilevanza, prezzo e qualita del dato."
        )

    if parsed.category:
        return (
            f"Ho trovato {min(len(records), DEFAULT_CARD_LIMIT)} risultati per "
            f"{category_label(parsed.category)}.\n"
            "Le card sono ordinate per rilevanza e valore reale."
        )

    return (
        f"Ho trovato {min(len(records), DEFAULT_CARD_LIMIT)} prodotti rilevanti.\n"
        "Le card mostrano le migliori offerte reali disponibili."
    )


def available_categories_text():
    return "TV, cuffie, smartphone, laptop e casse audio"


def followup_text():
    return "Puoi chiedermi anche: \"cuffie sotto 100€\" oppure \"quando comprare questo prodotto?\""


def data_honesty(records=None, products_count=None, history_points=None):
    notes = []

    if records is not None:
        store_names = {
            record["offer"].get("store_name")
            for record in records
            if record.get("offer")
        }
        store_names = {store for store in store_names if store}

        if len(store_names) == 1:
            notes.append(
                f"Confronto limitato: al momento ho dati utilizzabili solo da {next(iter(store_names))}."
            )
        elif len(store_names) > 1:
            notes.append(f"Confronto basato su {len(store_names)} store.")

        if products_count is not None and products_count <= 3:
            notes.append("Campione piccolo: potrebbero mancare alternative nel database.")

    if history_points is not None and history_points < DEFAULT_HISTORY_MIN_POINTS:
        notes.append("Storico prezzi ancora limitato: non considero affidabile una previsione.")

    if not notes:
        return "Dati: uso solo prodotti, offerte e storico reali presenti in Supabase."

    return " ".join(notes)


def offer_reason(record, prefix="Motivo"):
    reasons = []

    if record.get("discount_pct"):
        reasons.append(f"sconto reale {record['discount_pct']:.1f}%")

    confidence = record["offer"].get("data_confidence")
    if confidence:
        reasons.append(f"dato {confidence}")

    if not reasons:
        reasons.append("prezzo piu basso tra i dati disponibili")

    return f"{prefix}: {', '.join(reasons)}."


def format_offer_line(record, index=None):
    product = record["product"]
    offer = record["offer"]
    bullet = f"{index}. " if index is not None else "- "

    return (
        f"{bullet}{product_label(product)}\n"
        f"   Store: {offer['store_name']} | Prezzo: {format_price(record['price'])}\n"
        f"   {offer_reason(record)}"
    )


def format_top_records(records):
    return "\n".join(
        format_offer_line(record, index=index)
        for index, record in enumerate(records[:3], start=1)
    )


def no_products_response(parsed, original_question):
    category_hint = f" nella categoria {category_label(parsed.category)}" if parsed.category else ""
    query = parsed.query or original_question

    return (
        f"Non ho trovato prodotti reali{category_hint} per \"{query}\".\n"
        f"Categorie disponibili: {available_categories_text()}.\n"
        "Prova con marca, modello o budget. Non invento prezzi o retailer.\n"
        f"{followup_text()}"
    )


def answer_best_under_budget(parsed):
    products = search_products(
        parsed.query,
        limit=80,
        category=parsed.category,
        keywords=(),
    )
    records = collect_offer_records(products, budget=parsed.budget)
    records.sort(key=lambda item: item["price"])
    top_records = records[:3]

    if not top_records:
        return (
            f"Non ho trovato offerte reali per {category_label(parsed.category)} "
            f"sotto {format_price(parsed.budget)} nei dati attuali.\n"
            f"Categorie disponibili: {available_categories_text()}.\n"
            f"{followup_text()}"
        )

    winner = top_records[0]
    lines = [
        f"La scelta migliore sotto {format_price(parsed.budget)} e "
        f"{product_label(winner['product'])} a {format_price(winner['price'])} "
        f"da {winner['offer']['store_name']}.",
        "",
        "Top 3 opzioni:",
        format_top_records(top_records),
    ]
    lines.append(
        f"\nPerche: ha il prezzo piu basso attualmente tracciato in questa ricerca."
    )
    lines.append(
        f"{data_honesty(records=records, products_count=len(products))} "
        f"Ho usato {len(records)} offerte sotto budget."
    )
    lines.append(followup_text())

    return "\n".join(lines)


def answer_cheapest_offer(parsed, products):
    records = collect_offer_records(products)
    records.sort(key=lambda item: item["price"])

    if not records:
        return (
            f"Ho trovato prodotti per \"{parsed.query or category_label(parsed.category)}\", "
            "ma non ho offerte disponibili con prezzo valido nei dati attuali.\n"
            f"Categorie disponibili: {available_categories_text()}.\n"
            f"{followup_text()}"
        )

    winner = records[0]
    offer = winner["offer"]
    product = winner["product"]

    lines = [
        f"Il prezzo piu basso che ho trovato e {format_price(winner['price'])} "
        f"da {offer['store_name']} per {product_label(product)}.",
        f"Perche: e il prezzo minimo tra le offerte utilizzabili per questa ricerca.",
    ]

    if len(records) > 1:
        lines.append("\nTop 3 opzioni:")
        lines.append(format_top_records(records))

    lines.append(
        f"\n{data_honesty(records=records, products_count=len(products))} "
        f"Offerte utilizzabili: {len(records)}. "
        f"Data confidence migliore offerta: {offer.get('data_confidence') or 'non indicata'}."
    )
    lines.append(followup_text())

    return "\n".join(lines)


def answer_when_to_buy(parsed, products):
    product = products[0]
    best_offer = get_best_offer(product.get("id"))
    context = get_price_context(product.get("id"))

    if context["history_points"] < DEFAULT_HISTORY_MIN_POINTS:
        best_offer_text = ""
        if best_offer:
            best_offer_text = (
                f" Prezzo attuale migliore: {best_offer['store_name']} "
                f"a {format_price(best_offer['price'])}."
            )

        return (
            f"Non ho ancora abbastanza storico per dire quando conviene comprare "
            f"{product_label(product)}.{best_offer_text}\n"
            f"{data_honesty(history_points=context['history_points'])} "
            f"Punti storico validi: {context['history_points']}.\n"
            f"{followup_text()}"
        )

    prediction = get_prediction_for_product(product, best_offer)

    if not prediction:
        return (
            f"Non ho ancora una previsione affidabile per {product_label(product)}.\n"
            f"Ho {context['history_points']} punti storici complessivi, ma non abbastanza "
            "storico affidabile sullo store della miglior offerta.\n"
            f"{followup_text()}"
        )

    return (
        f"Per {product_label(product)}: {prediction.recommendation}.\n"
        f"Miglior prezzo attuale: {best_offer['store_name']} a {format_price(best_offer['price'])}.\n"
        f"Perche: {prediction.reason}\n"
        f"{data_honesty(history_points=context['history_points'])} "
        f"Storico={context['history_points']} punti, min={format_price(context['min_price'])}, "
        f"media={format_price(context['avg_price'])}, confidence={prediction.confidence}.\n"
        f"{followup_text()}"
    )


def answer_category_recommendation(parsed):
    products = search_products(
        parsed.query,
        limit=80,
        category=parsed.category,
        keywords=parsed.keywords,
    )
    records = collect_offer_records(products, budget=parsed.budget)
    records.sort(key=lambda item: item["price"])
    top_records = records[:3]

    if not top_records:
        return (
            f"Non ho trovato offerte reali abbastanza coerenti per "
            f"{category_label(parsed.category)}.\n"
            f"Categorie disponibili: {available_categories_text()}.\n"
            f"{followup_text()}"
        )

    budget_text = f" sotto {format_price(parsed.budget)}" if parsed.budget else ""
    winner = top_records[0]
    lines = [
        f"La scelta piu conveniente per {category_label(parsed.category)}{budget_text} "
        f"e {product_label(winner['product'])} a {format_price(winner['price'])} "
        f"da {winner['offer']['store_name']}.",
        "",
        "Top 3 opzioni:",
        format_top_records(top_records),
    ]
    lines.append(
        "\nPerche: e il prezzo piu basso tra i risultati tracciati."
    )
    lines.append(
        f"{data_honesty(records=records, products_count=len(products))} "
        f"Offerte utilizzabili: {len(records)}."
    )
    lines.append(followup_text())

    return "\n".join(lines)


def answer_discount_ranking(parsed):
    products = search_products(
        parsed.query,
        limit=120,
        category=parsed.category,
        keywords=parsed.keywords,
    )

    if not products:
        products = fetch_products()

    records = [
        record
        for record in collect_offer_records(products)
        if record["discount_pct"] is not None and record["discount_pct"] > 0
    ]
    records.sort(key=lambda item: (-item["discount_pct"], item["price"]))
    top_records = records[:3]

    if not top_records:
        return (
            "Non ho trovato sconti reali calcolabili: serve old_price maggiore "
            "del prezzo attuale. Non invento percentuali di sconto.\n"
            f"{followup_text()}"
        )

    winner = top_records[0]
    lines = [
        f"Lo sconto migliore nei dati reali e {winner['discount_pct']:.1f}% su "
        f"{product_label(winner['product'])}: ora {format_price(winner['price'])} "
        f"da {winner['offer']['store_name']}.",
        "",
        "Top 3 sconti:",
    ]

    for index, record in enumerate(top_records, start=1):
        lines.append(
            f"{index}. {product_label(record['product'])}\n"
            f"   Store: {record['offer']['store_name']} | Prezzo: {format_price(record['price'])}\n"
            f"   Motivo: sconto reale {record['discount_pct']:.1f}% "
            f"da {format_price(record['old_price'])}."
        )

    lines.append(
        f"\n{data_honesty(records=records)} Offerte con old_price valido: {len(records)}."
    )
    lines.append(followup_text())
    return "\n".join(lines)


def answer_product_search(parsed, products):
    records = collect_offer_records(products)

    if not records:
        return (
            f"Ho trovato {len(products)} prodotto/i per \"{parsed.query}\", "
            "ma nessuna offerta valida disponibile ora.\n"
            f"{followup_text()}"
        )

    records.sort(key=lambda item: item["price"])
    top_records = records[:3]
    winner = top_records[0]
    lines = [
        f"Ho trovato {len(products)} prodotto/i coerenti. Il piu conveniente e "
        f"{product_label(winner['product'])} a {format_price(winner['price'])} "
        f"da {winner['offer']['store_name']}.",
        "",
        "Top 3 opzioni:",
        format_top_records(top_records),
    ]

    lines.append(
        f"\n{data_honesty(records=records, products_count=len(products))} "
        f"Offerte utilizzabili: {len(records)}."
    )
    lines.append(followup_text())

    return "\n".join(lines)


def answer_question_from_parsed(question, parsed):
    if parsed.intent == "unknown":
        return (
            "Non ho capito bene la domanda.\n"
            f"Categorie disponibili: {available_categories_text()}.\n"
            "Prova con: \"tv sotto i 500 euro\", \"dove costa meno AirPods\" "
            "o \"quale prodotto ha lo sconto migliore\"."
        )

    products, records = products_and_records_for_parsed(parsed)
    return short_answer_for_results(parsed, products, records, question)


def answer_question(question):
    return answer_question_from_parsed(question, parse_question(question))


def products_for_question(question):
    parsed = parse_question(question)
    _, records = products_and_records_for_parsed(parsed)
    return product_cards_from_records(records)


def sanitize_llm_reason(reason):
    if not isinstance(reason, str):
        return None

    reason = re.sub(r"\s+", " ", reason).strip()
    if not reason:
        return None

    if "€" in reason:
        return None

    if len(reason) > 140:
        reason = reason[:137].rstrip() + "..."

    return reason


def llm_reasons_by_product_id(llm_response, valid_product_ids):
    reasons = {}

    for item in llm_response.get("product_reasons") or []:
        if not isinstance(item, dict):
            continue

        product_id = item.get("product_id")
        if product_id not in valid_product_ids:
            continue

        reason = sanitize_llm_reason(item.get("reason"))
        if reason:
            reasons[product_id] = reason

    return reasons


def ranked_cards_from_llm(candidate_cards, llm_response):
    cards_by_id = {
        card.get("product_id"): card
        for card in candidate_cards
        if card.get("product_id")
    }
    valid_product_ids = set(cards_by_id.keys())
    reasons = llm_reasons_by_product_id(llm_response, valid_product_ids)
    ranked_cards = []
    seen_product_ids = set()

    for product_id in llm_response.get("ranked_product_ids") or []:
        if product_id not in cards_by_id or product_id in seen_product_ids:
            continue

        card = dict(cards_by_id[product_id])
        if product_id in reasons:
            card["reason"] = reasons[product_id]
        ranked_cards.append(card)
        seen_product_ids.add(product_id)

        if len(ranked_cards) >= DEFAULT_CARD_LIMIT:
            break

    for card in candidate_cards:
        product_id = card.get("product_id")
        if product_id in seen_product_ids:
            continue

        card = dict(card)
        if product_id in reasons:
            card["reason"] = reasons[product_id]
        ranked_cards.append(card)
        seen_product_ids.add(product_id)

        if len(ranked_cards) >= DEFAULT_CARD_LIMIT:
            break

    return ranked_cards


def concise_answer_from_cards(parsed, cards):
    if not cards:
        return None

    category = category_label(parsed.category) if parsed.category else "risultati"
    budget_text = f" sotto {format_price(parsed.budget)}" if parsed.budget else ""

    if parsed.intent == "discount_ranking":
        title = "Migliori sconti reali trovati"
    elif parsed.intent == "when_to_buy":
        title = "Prezzo e storico disponibili"
    elif parsed.intent == "cheapest_offer":
        title = "Prezzo piu basso trovato"
    else:
        title = f"{category}{budget_text}: {len(cards)} opzioni reali"

    summary = "Le card sotto usano solo prodotti e offerte reali presenti in Supabase."
    return f"{title}\n{summary}"


def safe_llm_answer(llm_response, parsed, cards):
    if not isinstance(llm_response, dict):
        return None

    title = re.sub(r"\s+", " ", str(llm_response.get("answer_title") or "")).strip()
    summary = re.sub(r"\s+", " ", str(llm_response.get("answer_summary") or "")).strip()

    if not title:
        return None

    text = f"{title}\n{summary}" if summary else title

    if "€" in text:
        return concise_answer_from_cards(parsed, cards)

    if len(text) > 260:
        text = text[:257].rstrip() + "..."

    return text


def answer_question_payload(question):
    parsed = parse_question(question)
    _, records = products_and_records_for_parsed(parsed)
    candidate_cards = product_cards_from_records(records, limit=12)
    fallback_answer = answer_question_from_parsed(question, parsed)

    if not candidate_cards:
        return {
            "answer": fallback_answer,
            "products": [],
        }

    if looks_product_specific_parsed(parsed):
        return {
            "answer": answer_product_specific_match(parsed, records),
            "products": candidate_cards[:DEFAULT_CARD_LIMIT],
        }

    llm_response = generate_shopping_response_with_llm(
        question=question,
        parsed_payload=parsed_question_payload(parsed),
        product_cards=candidate_cards,
    )

    if llm_response:
        products = ranked_cards_from_llm(candidate_cards, llm_response)
        answer = safe_llm_answer(llm_response, parsed, products)
        if not answer:
            answer = concise_answer_from_cards(parsed, products) or fallback_answer
    else:
        products = candidate_cards[:DEFAULT_CARD_LIMIT]
        answer = fallback_answer

    return {
        "answer": answer,
        "products": products,
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description="Spario AI Shopping Assistant read-only."
    )
    parser.add_argument("question", help="Domanda naturale dell'utente")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        print(answer_question(args.question))
    except Exception as exc:
        print(f"ERRORE assistant detail={exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
