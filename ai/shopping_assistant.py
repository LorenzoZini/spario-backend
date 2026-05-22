import argparse
import re
import statistics
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from supabase import create_client

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

    if budget is not None and category:
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


def parse_question(question):
    normalized = normalize_text(question)
    category = detect_category(normalized)
    budget = detect_budget(normalized)
    keywords = tuple(useful_keywords(normalized))
    query = extract_query(normalized)
    intent = detect_intent(normalized, category, budget, keywords)

    return ParsedQuestion(
        intent=intent,
        query=query,
        normalized_question=normalized,
        category=category,
        budget=budget,
        keywords=keywords,
    )


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
    return any(alias in blob for alias in CATEGORY_ALIASES.get(category, []))


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
    products = fetch_products()
    scored = []

    for product in products:
        score = score_product(
            product,
            query=query,
            category=category,
            keywords=keywords,
        )
        if score <= 0:
            continue

        scored.append((score, product))

    scored.sort(key=lambda item: (-item[0], product_search_blob(item[1])))

    return [product for _, product in scored[:limit]]


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


def get_best_offer(product_id):
    offers = fetch_offers_for_product(product_id)
    stores_by_id = store_lookup()
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


def product_cards_from_records(records, limit=3):
    return [
        product_card_from_record(record)
        for record in records[:limit]
        if record.get("product") and record.get("offer")
    ]


def collect_offer_records(products, budget=None):
    records = []

    for product in products:
        record = offer_record(product, get_best_offer(product.get("id")))
        if not record:
            continue

        if budget is not None and record["price"] > budget:
            continue

        records.append(record)

    return records


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


def answer_question(question):
    parsed = parse_question(question)

    if parsed.intent == "unknown":
        return (
            "Non ho capito bene la domanda.\n"
            f"Categorie disponibili: {available_categories_text()}.\n"
            "Prova con: \"tv sotto i 500 euro\", \"dove costa meno AirPods\" "
            "o \"quale prodotto ha lo sconto migliore\"."
        )

    if parsed.intent == "discount_ranking":
        return answer_discount_ranking(parsed)

    if parsed.intent == "best_under_budget":
        return answer_best_under_budget(parsed)

    product_limit = 40 if parsed.intent in {"cheapest_offer", "category_recommendation"} else DEFAULT_PRODUCT_LIMIT
    products = search_products(
        parsed.query,
        limit=product_limit,
        category=parsed.category,
        keywords=parsed.keywords,
    )

    if not products:
        return no_products_response(parsed, question)

    if parsed.intent == "cheapest_offer":
        return answer_cheapest_offer(parsed, products)

    if parsed.intent == "when_to_buy":
        return answer_when_to_buy(parsed, products)

    if parsed.intent == "category_recommendation":
        return answer_category_recommendation(parsed)

    if parsed.intent == "product_search":
        return answer_product_search(parsed, products)

    return (
        "Non ho abbastanza informazioni per rispondere in modo affidabile usando "
        "solo i dati reali disponibili."
    )


def products_for_question(question):
    parsed = parse_question(question)

    if parsed.intent in {"unknown"}:
        return []

    if parsed.intent == "discount_ranking":
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
        return product_cards_from_records(records)

    if parsed.intent == "best_under_budget":
        products = search_products(
            parsed.query,
            limit=80,
            category=parsed.category,
            keywords=(),
        )
        records = collect_offer_records(products, budget=parsed.budget)
        records.sort(key=lambda item: item["price"])
        return product_cards_from_records(records)

    product_limit = 40 if parsed.intent in {"cheapest_offer", "category_recommendation"} else DEFAULT_PRODUCT_LIMIT
    products = search_products(
        parsed.query,
        limit=product_limit,
        category=parsed.category,
        keywords=parsed.keywords,
    )

    if not products:
        return []

    if parsed.intent == "when_to_buy":
        record = offer_record(products[0], get_best_offer(products[0].get("id")))
        return product_cards_from_records([record] if record else [])

    records = collect_offer_records(products, budget=parsed.budget)

    if parsed.intent == "discount_ranking":
        records = [
            record
            for record in records
            if record["discount_pct"] is not None and record["discount_pct"] > 0
        ]
        records.sort(key=lambda item: (-item["discount_pct"], item["price"]))
    else:
        records.sort(key=lambda item: item["price"])

    return product_cards_from_records(records)


def answer_question_payload(question):
    return {
        "answer": answer_question(question),
        "products": products_for_question(question),
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
