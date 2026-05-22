import argparse
import html as html_lib
import json
import re
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import requests
from importers.config import FIRECRAWL_API_KEY
from importers.utils import save_product_offer

# Firecrawl API: Search scopre URL candidati, Scrape legge markdown/html.
# Le search sono sempre batchate a massimo 30 risultati; HTTP 400 viene trattato
# come query/payload non valido, con fallback semplice e skip senza crash.
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"

RETAILER_NAME = "MediaWorld"
RETAILER_WEBSITE = "https://www.mediaworld.it"
RETAILER_TYPE = "tech"

HEADERS = {
    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
    "Content-Type": "application/json",
}

FIRECRAWL_TIMEOUT_SECONDS = 60
FIRECRAWL_MAX_RETRIES = 2
FIRECRAWL_SEARCH_BATCH_LIMIT = 30

MIN_VALID_PRICE = 5.0
MAX_VALID_PRICE = 5000.0

DISCARD_REASONS = {
    "no_title",
    "no_price",
    "bad_url",
    "out_of_stock",
    "low_confidence",
    "scrape_error",
    "search_bad_request",
}

CATEGORIES = {
    "smartphone": "site:mediaworld.it/it/category/smartphone-100101.html smartphone cellulari",
    "cuffie": "site:mediaworld.it/it/product auricolari bluetooth cuffie wireless",
    "laptop": "site:mediaworld.it/it/category/notebook-200101.html notebook laptop",
    "tv": "site:mediaworld.it/it/category/tv-4001.html smart tv televisori",
    "desktop": "site:mediaworld.it/it/category/all-in-one-200105.html pc desktop all-in-one",
    "casse_audio": "site:mediaworld.it/it/category/casse-bluetooth-100109.html casse bluetooth",
}

CATEGORY_SEARCH_QUERIES = {
    "smartphone": [
        "site:mediaworld.it/it/category/smartphone-100101.html smartphone cellulari",
        "site:mediaworld.it/it/category smartphone cellulari iphone samsung galaxy xiaomi",
        "site:mediaworld.it/it/product smartphone cellulari iphone samsung galaxy xiaomi",
        "site:mediaworld.it/it/product/_apple-iphone smartphone",
        "site:mediaworld.it/it/product/_samsung-galaxy smartphone",
        "site:mediaworld.it/it/product/_xiaomi smartphone",
        "site:mediaworld.it/it/product/_motorola smartphone",
        "site:mediaworld.it/it/product smartphone 5g 128gb 256gb",
        "site:mediaworld.it/it/product oppo honor realme smartphone",
    ],
    "cuffie": [
        "site:mediaworld.it/it/product auricolari bluetooth cuffie wireless",
        "site:mediaworld.it/it/category/auricolari-bluetooth-401102.html auricolari bluetooth",
        "site:mediaworld.it/it/category cuffie auricolari bluetooth",
        "site:mediaworld.it/it/product airpods sony jbl bose auricolari",
        "site:mediaworld.it/it/product true wireless earbuds cuffie",
    ],
    "laptop": [
        "site:mediaworld.it/it/category/computer-20.html notebook laptop",
        "site:mediaworld.it/it/category/notebook-200101.html notebook laptop portatili macbook",
        "site:mediaworld.it/it/category notebook laptop portatili macbook",
        "site:mediaworld.it/it/product notebook laptop pc portatile",
        "site:mediaworld.it/it/product/_apple-macbook notebook laptop",
        "site:mediaworld.it/it/product hp lenovo asus acer notebook",
        "site:mediaworld.it/it/product/_hp notebook laptop",
        "site:mediaworld.it/it/product/_lenovo notebook laptop",
        "site:mediaworld.it/it/product/_asus notebook laptop",
        "site:mediaworld.it/it/product/_acer notebook laptop",
        "site:mediaworld.it/it/product macbook laptop 16gb ssd",
    ],
    "tv": [
        "site:mediaworld.it/it/category/tv-4001.html smart tv televisore",
        "site:mediaworld.it/it/category/tv-4001.html TV Smart TV televisori OLED QLED",
        "site:mediaworld.it/it/category/tv-qled-400105.html qled smart tv",
        "site:mediaworld.it/it/category tv oled qled smart tv televisori",
        "site:mediaworld.it/it/product smart tv televisore 4k",
        "site:mediaworld.it/it/product/_televisore smart tv",
        "site:mediaworld.it/it/product oled qled led tv",
        "site:mediaworld.it/it/product/_samsung tv qled",
        "site:mediaworld.it/it/product/_lg oled tv",
        "site:mediaworld.it/it/product/_sony bravia tv",
        "site:mediaworld.it/it/product samsung lg sony smart tv",
    ],
    "desktop": [
        "site:mediaworld.it/it/category/all-in-one-200105.html all-in-one pc desktop",
        "site:mediaworld.it/it/category/computer-20.html desktop pc computer fisso all-in-one",
        "site:mediaworld.it/it/category pc desktop computer gaming all-in-one",
        "site:mediaworld.it/it/product desktop pc computer fisso",
        "site:mediaworld.it/it/product/_pc-desktop pc desktop",
        "site:mediaworld.it/it/product/_pc-gaming gaming desktop",
        "site:mediaworld.it/it/product/_pc-desktop-monitor gaming desktop",
        "site:mediaworld.it/it/product/_all-in-one aio pc desktop",
        "site:mediaworld.it/it/product/_imac all-in-one desktop",
        "site:mediaworld.it/it/product hp lenovo desktop pc",
    ],
    "casse_audio": [
        "site:mediaworld.it/it/category/casse-bluetooth-100109.html speaker bluetooth casse",
        "site:mediaworld.it/it/category casse bluetooth altoparlanti speaker jbl",
        "site:mediaworld.it/it/product casse bluetooth speaker audio",
        "site:mediaworld.it/it/product/_cassa-bluetooth speaker bluetooth",
        "site:mediaworld.it/it/product/_cassa-wireless speaker bluetooth",
        "site:mediaworld.it/it/product/_speaker bluetooth altoparlanti",
        "site:mediaworld.it/it/product jbl sony bose speaker bluetooth",
        "site:mediaworld.it/it/product/_jbl speaker bluetooth",
        "site:mediaworld.it/it/product/_party-speaker casse bluetooth",
        "site:mediaworld.it/it/product cassa bluetooth portatile",
    ],
}

CATEGORY_SEED_URLS = {
    "smartphone": [
        "https://www.mediaworld.it/it/category/smartphone-100101.html",
    ],
    "cuffie": [
        "https://www.mediaworld.it/it/category/auricolari-bluetooth-401102.html",
    ],
    "laptop": [
        "https://www.mediaworld.it/it/category/computer-20.html",
        "https://www.mediaworld.it/it/category/notebook-200101.html",
    ],
    "tv": [
        "https://www.mediaworld.it/it/category/tv-4001.html",
        "https://www.mediaworld.it/it/category/tv-qled-400105.html",
    ],
    "desktop": [
        "https://www.mediaworld.it/it/category/computer-20.html",
        "https://www.mediaworld.it/it/category/all-in-one-200105.html",
    ],
    "casse_audio": [
        "https://www.mediaworld.it/it/category/casse-bluetooth-100109.html",
    ],
}


class FirecrawlBadRequestError(Exception):
    def __init__(self, endpoint, payload, body):
        self.endpoint = endpoint
        self.payload = payload
        self.body = body
        super().__init__(body)


def clean_text(value):
    if not value:
        return ""

    value = html_lib.unescape(str(value))
    value = unquote(value)
    value = value.replace("\\/", "/")
    value = value.replace("\\|", "|")
    value = value.replace("\\u002F", "/")
    value = value.replace("\\", "")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def log_discard(reason, url, detail=None):
    if reason not in DISCARD_REASONS:
        reason = "scrape_error"

    message = f"SCARTATO reason={reason} url={url}"
    if detail:
        message += f" detail={clean_text(detail)}"

    print(message)


def response_body_preview(response, max_length=1200):
    try:
        body = response.text
    except Exception:
        body = ""

    body = clean_text(body)

    if len(body) > max_length:
        return f"{body[:max_length]}..."

    return body


def log_firecrawl_response_error(endpoint, payload, response):
    body = response_body_preview(response)
    safe_payload = json.dumps(payload, ensure_ascii=False)

    if len(safe_payload) > 1000:
        safe_payload = f"{safe_payload[:1000]}..."

    print(
        "Firecrawl response non-200 "
        f"status={response.status_code} endpoint={endpoint} "
        f"payload={safe_payload} body={body}"
    )


def firecrawl_post(endpoint, payload, attempt=1):
    try:
        response = requests.post(
            endpoint,
            headers=HEADERS,
            json=payload,
            timeout=FIRECRAWL_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout:
        if attempt <= FIRECRAWL_MAX_RETRIES:
            wait_seconds = 10 * attempt
            print(f"Timeout Firecrawl. Ritento tra {wait_seconds} secondi...")
            time.sleep(wait_seconds)
            return firecrawl_post(endpoint, payload, attempt + 1)
        raise
    except requests.exceptions.RequestException:
        raise

    if response.status_code != 200:
        log_firecrawl_response_error(endpoint, payload, response)

    if response.status_code == 400:
        raise FirecrawlBadRequestError(
            endpoint=endpoint,
            payload=payload,
            body=response_body_preview(response),
        )

    if response.status_code == 429 and attempt <= FIRECRAWL_MAX_RETRIES + 2:
        wait_seconds = 60 * attempt
        print(f"Rate limit Firecrawl. Attendo {wait_seconds} secondi...")
        time.sleep(wait_seconds)
        return firecrawl_post(endpoint, payload, attempt + 1)

    if response.status_code >= 500 and attempt <= FIRECRAWL_MAX_RETRIES:
        wait_seconds = 10 * attempt
        print(f"Errore Firecrawl {response.status_code}. Ritento tra {wait_seconds} secondi...")
        time.sleep(wait_seconds)
        return firecrawl_post(endpoint, payload, attempt + 1)

    response.raise_for_status()
    return response.json()


def simplify_search_query(query):
    tokens = []

    for token in query.split():
        if token.startswith("site:"):
            continue

        cleaned = re.sub(r"[^a-zA-Z0-9àèéìòùÀÈÉÌÒÙ-]", "", token).strip()
        if cleaned:
            tokens.append(cleaned)

    if not tokens:
        tokens = ["mediaworld", "prodotti"]

    return f"site:mediaworld.it/it/product {' '.join(tokens[:8])}"


def firecrawl_search(query, limit=10):
    safe_limit = min(max(int(limit), 1), FIRECRAWL_SEARCH_BATCH_LIMIT)
    payload = {
        "query": query,
        "limit": safe_limit,
        "sources": ["web"],
    }

    try:
        return firecrawl_post(FIRECRAWL_SEARCH_URL, payload)
    except FirecrawlBadRequestError as e:
        log_discard("search_bad_request", f"search:{query}", e.body)
    except Exception as e:
        log_discard("scrape_error", f"search:{query}", str(e))
        return {"data": []}

    fallback_query = simplify_search_query(query)

    if fallback_query == query:
        return {"data": []}

    fallback_payload = {
        "query": fallback_query,
        "limit": safe_limit,
        "sources": ["web"],
    }

    print(f"Fallback Firecrawl search: {fallback_query}")

    try:
        return firecrawl_post(FIRECRAWL_SEARCH_URL, fallback_payload)
    except FirecrawlBadRequestError as e:
        log_discard("search_bad_request", f"search:{fallback_query}", e.body)
        return {"data": []}
    except Exception as e:
        log_discard("scrape_error", f"search:{fallback_query}", str(e))
        return {"data": []}


def firecrawl_scrape(url):
    payload = {
        "url": url,
        "formats": ["markdown", "html"],
    }

    return firecrawl_post(FIRECRAWL_SCRAPE_URL, payload)


def extract_items(results):
    if isinstance(results, list):
        return results

    if not isinstance(results, dict):
        return []

    data = results.get("data", [])

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ["web", "results", "items"]:
            if isinstance(data.get(key), list):
                return data.get(key)

    return []


# Discovery URL: accetta solo pagine prodotto MediaWorld /it/product/...html,
# canonicalizza togliendo query/fragment e usa listing/category solo come fonte link.
def normalize_mediaworld_url(url):
    if not url:
        return None

    url = clean_text(url)

    if url.startswith("//"):
        url = f"https:{url}"

    if url.startswith("/"):
        url = urljoin(RETAILER_WEBSITE, url)

    parsed = urlsplit(url)
    netloc = parsed.netloc.lower()

    if netloc not in {"www.mediaworld.it", "mediaworld.it"}:
        return None

    path = parsed.path
    if not path:
        return None

    return urlunsplit(("https", "www.mediaworld.it", path, "", ""))


def is_product_url(url):
    if not url:
        return False

    parsed = urlsplit(url)
    path = parsed.path.lower()

    return path.startswith("/it/product/") and path.endswith(".html")


def is_listing_url(url):
    if not url:
        return False

    parsed = urlsplit(url)
    path = parsed.path.lower()

    if parsed.netloc.lower() not in {"www.mediaworld.it", "mediaworld.it"}:
        return False

    if is_product_url(url):
        return False

    excluded_paths = [
        "/it/account",
        "/it/cart",
        "/it/checkout",
        "/it/customer",
        "/it/login",
        "/it/service",
        "/it/store",
    ]

    if any(token in path for token in excluded_paths):
        return False

    return (
        path.startswith("/it/category/")
        or path.startswith("/it/search")
        or path.startswith("/it/campaign/")
    )


def extract_product_code(url):
    if not url:
        return None

    path = urlsplit(url).path
    if not path:
        return None

    slug = path.rstrip("/").split("/")[-1]
    slug = re.sub(r"\.html$", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]", "", slug.lower())

    return slug or None


def extract_product_urls_from_listing_text(text):
    if not text:
        return []

    normalized = clean_text(text)
    pattern = (
        r"(?:https?://(?:www\.)?mediaworld\.it)?"
        r"/it/product/[^\"'\s<>\)\]]+?\.html"
    )

    urls = []
    seen = set()

    for match in re.findall(pattern, normalized, flags=re.IGNORECASE):
        url = normalize_mediaworld_url(match)

        if not is_product_url(url):
            continue

        if url in seen:
            continue

        urls.append(url)
        seen.add(url)

    return urls


def get_product_urls_from_listing(url):
    scraped = firecrawl_scrape(url)
    data = scraped.get("data", scraped)

    markdown = data.get("markdown", "") if isinstance(data, dict) else ""
    html = data.get("html", "") if isinstance(data, dict) else ""

    return extract_product_urls_from_listing_text(f"{markdown}\n{html}")


def add_listing_candidate(listing_urls, seen_listing_urls, url):
    url = normalize_mediaworld_url(url)

    if not is_listing_url(url):
        return False

    if url in seen_listing_urls:
        return False

    listing_urls.append(url)
    seen_listing_urls.add(url)

    return True


def add_product_candidate(candidates, seen_urls, url, search_title=None, search_description=None):
    url = normalize_mediaworld_url(url)

    if not is_product_url(url):
        return False

    if url in seen_urls:
        return False

    candidates.append({
        "url": url,
        "search_title": search_title,
        "search_description": search_description,
    })
    seen_urls.add(url)

    return True


def get_product_candidates_for_category(category_key, limit=10):
    if category_key not in CATEGORIES:
        raise ValueError(f"Categoria non supportata: {category_key}")

    candidates = []
    listing_urls = []
    seen_urls = set()
    seen_listing_urls = set()
    queries_attempted = 0
    listing_product_urls_found = 0

    for seed_url in CATEGORY_SEED_URLS.get(category_key, []):
        add_listing_candidate(listing_urls, seen_listing_urls, seed_url)

    search_queries = CATEGORY_SEARCH_QUERIES.get(category_key, [CATEGORIES[category_key]])

    for query in search_queries:
        if len(candidates) >= limit:
            break

        batch_limit = min(limit - len(candidates), FIRECRAWL_SEARCH_BATCH_LIMIT)
        print(f"Search Firecrawl: limit={batch_limit} query={query}")
        queries_attempted += 1

        results = firecrawl_search(query, limit=batch_limit)
        items = extract_items(results)

        for item in items:
            if not isinstance(item, dict):
                continue

            raw_url = item.get("url") or item.get("link") or ""
            url = normalize_mediaworld_url(raw_url)
            search_title = item.get("title")
            search_description = item.get("description") or item.get("snippet")

            if not url:
                log_discard("bad_url", raw_url, "Risultato search non MediaWorld")
                continue

            if is_product_url(url):
                add_product_candidate(
                    candidates,
                    seen_urls,
                    url,
                    search_title=search_title,
                    search_description=search_description,
                )

                if len(candidates) >= limit:
                    break

                continue

            if is_listing_url(url):
                add_listing_candidate(listing_urls, seen_listing_urls, url)
                continue

            log_discard("bad_url", raw_url, "Risultato search non prodotto")

    for listing_url in listing_urls:
        if len(candidates) >= limit:
            break

        print(f"Scrape listing MediaWorld: {listing_url}")

        try:
            product_urls = get_product_urls_from_listing(listing_url)
        except Exception as e:
            log_discard("scrape_error", listing_url, str(e))
            continue

        listing_product_urls_found += len(product_urls)

        if not product_urls:
            log_discard("bad_url", listing_url, "Listing senza prodotti")
            continue

        for product_url in product_urls:
            add_product_candidate(candidates, seen_urls, product_url)

            if len(candidates) >= limit:
                break

    print(
        "Discovery MediaWorld "
        f"category={category_key} "
        f"query_provate={queries_attempted}/{len(search_queries)} "
        f"url_categoria_trovati={len(seen_listing_urls)} "
        f"url_prodotti_da_listing={listing_product_urls_found} "
        f"url_prodotti_estratti={len(seen_urls)}"
    )

    return candidates


def get_product_urls_for_category(category_key, limit=10):
    return [candidate["url"] for candidate in get_product_candidates_for_category(category_key, limit)]


def parse_decimal_price(value):
    if value is None:
        return None

    raw = clean_text(value)
    raw = raw.replace("€", "").replace("EUR", "").replace("eur", "")
    raw = re.sub(r"[^\d,.]", "", raw)

    if not raw:
        return None

    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    elif re.match(r"^\d{1,3}\.\d{3}$", raw):
        raw = raw.replace(".", "")

    try:
        price = float(raw)
    except ValueError:
        return None

    if MIN_VALID_PRICE <= price <= MAX_VALID_PRICE:
        return price

    return None


def extract_euro_prices(value):
    value = clean_text(value)
    matches = []
    matches.extend(re.findall(r"€\s*(\d{1,4}(?:[.,]\d{2})?)", value))
    matches.extend(re.findall(r"(\d{1,4}(?:[.,]\d{2})?)\s?€", value))

    prices = []

    for match in matches:
        price = parse_decimal_price(match)
        if price is not None:
            prices.append(price)

    return prices


def iter_json_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_json_objects(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_json_objects(item)


def parse_json_ld_blocks(text):
    blocks = []

    for match in re.finditer(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        text or "",
        re.IGNORECASE | re.DOTALL,
    ):
        raw = html_lib.unescape(match.group(1)).strip()
        if not raw:
            continue

        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    return blocks


def is_product_json(value):
    json_type = value.get("@type") or value.get("type")

    if isinstance(json_type, list):
        return any(str(item).lower() == "product" for item in json_type)

    return str(json_type).lower() == "product"


def extract_json_ld_product(text):
    for block in parse_json_ld_blocks(text):
        for value in iter_json_objects(block):
            if isinstance(value, dict) and is_product_json(value):
                return value

    return None


def get_offer_dict(product):
    if not isinstance(product, dict):
        return {}

    offers = product.get("offers")

    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    if isinstance(offers, dict):
        return offers

    return {}


def extract_price_from_offer(offer):
    if not isinstance(offer, dict):
        return None

    candidates = [
        offer.get("price"),
        offer.get("lowPrice"),
        offer.get("highPrice"),
    ]

    price_spec = offer.get("priceSpecification")
    if isinstance(price_spec, dict):
        candidates.append(price_spec.get("price"))

    if isinstance(price_spec, list):
        for item in price_spec:
            if isinstance(item, dict):
                candidates.append(item.get("price"))

    for candidate in candidates:
        price = parse_decimal_price(candidate)
        if price is not None:
            return price

    return None


def extract_json_ld_price(text):
    product = extract_json_ld_product(text)
    if not product:
        return None

    return extract_price_from_offer(get_offer_dict(product))


def extract_json_ld_title(text):
    product = extract_json_ld_product(text)
    if not product:
        return None

    return clean_title(product.get("name"))


def extract_json_ld_image(text):
    product = extract_json_ld_product(text)
    if not product:
        return None

    image = product.get("image")

    if isinstance(image, list):
        image = image[0] if image else None

    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")

    return normalize_image_url(image)


def get_metadata_value(metadata, *keys):
    if not isinstance(metadata, dict):
        return None

    lower_metadata = {
        str(key).lower(): value
        for key, value in metadata.items()
        if value is not None
    }

    for key in keys:
        value = metadata.get(key)
        if value:
            return value

        value = lower_metadata.get(str(key).lower())
        if value:
            return value

    return None


def extract_metadata_price(metadata):
    for candidate in [
        get_metadata_value(metadata, "product:price:amount", "og:price:amount"),
        get_metadata_value(metadata, "price", "twitter:data1"),
    ]:
        price = parse_decimal_price(candidate)
        if price is not None:
            return price

    return None


def extract_embedded_product_price(text):
    if not text:
        return None

    normalized = clean_text(text)
    patterns = [
        r'"(?:salePrice|currentPrice|finalPrice|price)"\s*:\s*"?(\d{1,4}(?:[.,]\d{1,2})?)"?',
        r'"(?:value|amount)"\s*:\s*"?(\d{1,4}(?:[.,]\d{1,2})?)"?\s*,\s*"(?:currency|currencyCode)"\s*:\s*"EUR"',
        r'"(?:currency|currencyCode)"\s*:\s*"EUR"\s*,\s*"(?:value|amount|price)"\s*:\s*"?(\d{1,4}(?:[.,]\d{1,2})?)"?',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            start = max(0, match.start() - 300)
            end = min(len(normalized), match.end() + 300)
            context = normalized[start:end].lower()

            if not any(token in context for token in ["product", "sku", "offer", "availability", "eur"]):
                continue

            if any(token in context for token in ["shipping", "spedizione", "delivery", "installment"]):
                continue

            price = parse_decimal_price(match.group(1))
            if price is not None:
                return price

    return None


def parse_contextual_euro_price(markdown, html):
    excluded_context = [
        "bonifico",
        "consegna",
        "finanziamento",
        "interessi",
        "klarna",
        "paypal",
        "punti",
        "recensione",
        "reso",
        "ritiro",
        "spedizione",
        "taeg",
        "tan",
    ]

    text = f"{markdown}\n{html}"
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]

    priority_tokens = [
        "prezzo",
        "iva inclusa",
        "aggiungi al carrello",
        "disponibile online",
        "offerta",
    ]

    for line in lines:
        lower = line.lower()

        if any(token in lower for token in excluded_context):
            continue

        if not any(token in lower for token in priority_tokens):
            continue

        prices = extract_euro_prices(line)
        if prices:
            return prices[0]

    for line in lines:
        lower = line.lower()

        if any(token in lower for token in excluded_context):
            continue

        prices = extract_euro_prices(line)
        if prices:
            return prices[0]

    return None


# Parsing prezzo: JSON-LD/meta/embedded data sono alta confidenza; fallback euro
# contestuale resta media. La confidenza bassa viene scartata prima del salvataggio.
def parse_price(html, markdown, metadata=None):
    text = f"{html}\n{markdown}"

    for candidate in [
        extract_json_ld_price(html),
        extract_json_ld_price(markdown),
        extract_metadata_price(metadata or {}),
        extract_embedded_product_price(text),
    ]:
        if candidate is not None:
            return candidate, "alta"

    fallback_price = parse_contextual_euro_price(markdown, html)
    if fallback_price is not None:
        return fallback_price, "media"

    return None, "bassa"


def parse_old_price(html, markdown, current_price=None):
    text = clean_text(f"{html}\n{markdown}")

    patterns = [
        r"prezzo\s+precedente\s*€?\s*(\d{1,4}(?:[.,]\d{2})?)",
        r"prezzo\s+consigliato\s*€?\s*(\d{1,4}(?:[.,]\d{2})?)",
        r"anzich[eé]\s*€?\s*(\d{1,4}(?:[.,]\d{2})?)",
        r"invece\s+di\s*€?\s*(\d{1,4}(?:[.,]\d{2})?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue

        price = parse_decimal_price(match.group(1))
        if price is None:
            continue

        if current_price is None or price >= current_price:
            return price

    return None


# Parsing titolo: preferisce JSON-LD/meta/H1 reali e scarta titoli generici MediaWorld.
def clean_title(value):
    title = clean_text(value)

    if not title:
        return None

    title = re.sub(r"\s*\|\s*MediaWorld(?:\.it)?\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*-\s*MediaWorld(?:\.it)?\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\|\s*Offerte.*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*Acquista online.*$", "", title, flags=re.IGNORECASE)
    title = clean_text(title)

    generic_titles = {
        "accesso",
        "account",
        "carrello",
        "categoria",
        "dettagli",
        "login",
        "mediaworld",
        "mediaworld.it",
        "pagina non trovata",
        "product",
        "prodotto",
        "risultati ricerca",
    }

    if title.lower() in generic_titles:
        return None

    if len(title) < 4:
        return None

    return title


def extract_heading_title(markdown, html):
    for line in markdown.splitlines():
        line = clean_text(line)

        if not line.startswith("#"):
            continue

        title = clean_title(re.sub(r"^#+\s*", "", line))
        if title:
            return title

    for match in re.finditer(r"<h1[^>]*>(.*?)</h1>", html or "", flags=re.IGNORECASE | re.DOTALL):
        title = clean_title(re.sub(r"<[^>]+>", " ", match.group(1)))
        if title:
            return title

    return None


def extract_title(html, markdown, metadata=None, search_title=None):
    metadata = metadata or {}

    for candidate in [
        extract_json_ld_title(html),
        extract_json_ld_title(markdown),
        get_metadata_value(metadata, "og:title", "twitter:title", "title"),
        extract_heading_title(markdown, html),
        search_title,
    ]:
        title = clean_title(candidate)
        if title:
            return title

    for line in markdown.splitlines():
        line = clean_text(line)
        if not line.startswith("!["):
            continue

        match = re.search(r"!\[(.*?)\]", line)
        if match:
            title = clean_title(match.group(1))
            if title:
                return title

    return None


def normalize_image_url(url):
    if not url:
        return None

    url = clean_text(url)

    if url.startswith("//"):
        return f"https:{url}"

    if url.startswith("/"):
        return urljoin(RETAILER_WEBSITE, url)

    if url.startswith("http://") or url.startswith("https://"):
        return url

    return None


def extract_image(html, markdown, metadata=None):
    metadata = metadata or {}

    for candidate in [
        get_metadata_value(metadata, "og:image", "twitter:image", "image"),
        extract_json_ld_image(html),
        extract_json_ld_image(markdown),
    ]:
        image_url = normalize_image_url(candidate)
        if image_url:
            return image_url

    combined = f"{html}\n{markdown}"
    match = re.search(r'https://[^"\s\)]+?\.(?:jpg|jpeg|png|webp)', combined, flags=re.IGNORECASE)

    if match:
        return match.group(0)

    return None


def normalize_availability(value):
    value = clean_text(value).lower()

    if not value:
        return "available"

    out_tokens = [
        "outofstock",
        "out_of_stock",
        "soldout",
        "sold out",
        "esaurito",
        "non disponibile",
        "temporaneamente non disponibile",
    ]

    if any(token in value for token in out_tokens):
        return "out_of_stock"

    available_tokens = [
        "instock",
        "in_stock",
        "lowstock",
        "low_stock",
        "preorder",
        "disponibile",
        "aggiungi al carrello",
    ]

    if any(token in value for token in available_tokens):
        return "available"

    return "available"


def extract_availability(html, markdown):
    for text in [html, markdown]:
        product = extract_json_ld_product(text)
        if not product:
            continue

        availability = normalize_availability(get_offer_dict(product).get("availability"))
        if availability:
            return availability

    normalized = clean_text(f"{html}\n{markdown}").lower()

    if any(
        token in normalized
        for token in [
            "outofstock",
            "non disponibile",
            "temporaneamente non disponibile",
            "prodotto non disponibile",
            "esaurito",
            "sold out",
        ]
    ):
        return "out_of_stock"

    return "available"


def extract_product_data(candidate, category_key):
    if isinstance(candidate, str):
        candidate = {"url": candidate}

    url = candidate.get("url")

    if not is_product_url(url):
        log_discard("bad_url", url, "URL non prodotto")
        return None

    scraped = firecrawl_scrape(url)
    data = scraped.get("data", scraped)

    markdown = data.get("markdown", "") if isinstance(data, dict) else ""
    html = data.get("html", "") if isinstance(data, dict) else ""
    metadata = data.get("metadata", {}) if isinstance(data, dict) else {}

    final_url = normalize_mediaworld_url(get_metadata_value(metadata, "url", "sourceURL"))
    if final_url and not is_product_url(final_url):
        log_discard("bad_url", url, f"Firecrawl ha restituito {final_url}")
        return None

    final_code = extract_product_code(final_url)
    requested_code = extract_product_code(url)
    if final_code and requested_code and final_code != requested_code:
        log_discard("bad_url", url, f"Firecrawl ha restituito product {final_code}")
        return None

    title = extract_title(
        html,
        markdown,
        metadata=metadata,
        search_title=candidate.get("search_title"),
    )

    if not title:
        log_discard("no_title", url)
        return None

    price, confidence = parse_price(html, markdown, metadata=metadata)

    if price is None:
        log_discard("no_price", url, title)
        return None

    if confidence == "bassa":
        log_discard("low_confidence", url, title)
        return None

    availability = extract_availability(html, markdown)

    if availability == "out_of_stock":
        log_discard("out_of_stock", url, title)
        return None

    image_url = extract_image(html, markdown, metadata=metadata)
    old_price = parse_old_price(html, markdown, current_price=price)

    return {
        "name": title,
        "category": category_key,
        "image_url": image_url,
        "price": price,
        "old_price": old_price,
        "url": url,
        "availability": availability,
        "data_confidence": confidence,
    }


# Import category loop: discovery batchata, scrape sequenziale, scarti sempre loggati.
def import_mediaworld_category(category_key, limit=10):
    print(f"Import categoria MediaWorld: {category_key}")

    candidates = get_product_candidates_for_category(category_key, limit=limit)
    print(f"URL prodotti trovati: {len(candidates)}")

    imported = 0

    for candidate in candidates:
        url = candidate["url"]
        print("\nScraping:", url)

        try:
            product = extract_product_data(candidate, category_key)

            if not product:
                continue

            # Salvataggio Supabase: il collector chiama solo save_product_offer().
            # La logica canonical product/offerta/storico resta centralizzata in utils.py.
            save_product_offer(
                name=product["name"],
                category=product["category"],
                image_url=product["image_url"],
                store_name=RETAILER_NAME,
                store_website=RETAILER_WEBSITE,
                store_type=RETAILER_TYPE,
                current_price=product["price"],
                old_price=product["old_price"],
                product_url=product["url"],
                availability=product["availability"],
                search_keywords=product["name"],
                condition="new",
                listing_type="retail_online",
                seller_feedback_percentage=None,
                data_confidence=product["data_confidence"],
            )

            imported += 1
            print(f"Importato: {product['name']} - €{product['price']} - {product['data_confidence']}")

            time.sleep(2)

        except Exception as e:
            log_discard("scrape_error", url, str(e))

    print(
        "\nImport completato. "
        f"category={category_key} prodotti_importati={imported}/{len(candidates)}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collector MediaWorld: importa offerte reali via Firecrawl e save_product_offer()."
    )

    parser.add_argument(
        "category",
        choices=CATEGORIES.keys(),
        help="Categoria da importare",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Numero massimo di prodotti validi da cercare",
    )

    args = parser.parse_args()

    import_mediaworld_category(args.category, limit=args.limit)
