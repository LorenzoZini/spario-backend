import argparse
import html as html_lib
import json
import re
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from importers.config import FIRECRAWL_API_KEY
from importers.utils import save_product_offer

# Firecrawl API: Search trova URL candidati, Scrape legge markdown/html delle pagine.
# Le search sono sempre limitate a batch piccoli; 400 viene gestito come query/payload non valido.
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"

RETAILER_NAME = "Unieuro"
RETAILER_WEBSITE = "https://www.unieuro.it"
RETAILER_TYPE = "tech"

HEADERS = {
    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
    "Content-Type": "application/json",
}

FIRECRAWL_TIMEOUT_SECONDS = 60
FIRECRAWL_MAX_RETRIES = 2
FIRECRAWL_SEARCH_BATCH_LIMIT = 30

CATEGORIES = {
    "smartphone": "site:unieuro.it/online/Smartphone smartphone",
    "cuffie": "site:unieuro.it/online/Cuffie-e-Auricolari cuffie auricolari",
    "laptop": "site:unieuro.it/online/Notebook notebook laptop",
    "tv": "site:unieuro.it/online/TV-DVD-e-Home-Cinema/TV smart tv televisore",
    "desktop": "site:unieuro.it/online/PC-Desktop desktop pc computer",
    "casse_audio": "site:unieuro.it/online/Audio-Ipod-e-Hi-Fi/Diffusori-Audio-Portatili/Diffusori-Bluetooth casse bluetooth speaker audio",
}

DISCARD_REASONS = {
    "no_title",
    "no_price",
    "bad_url",
    "search_bad_request",
    "out_of_stock",
    "low_confidence",
    "scrape_error",
}

MIN_VALID_PRICE = 5.0
MAX_VALID_PRICE = 5000.0

CATEGORY_SEARCH_QUERIES = {
    "smartphone": [
        "site:unieuro.it/online/Smartphone smartphone",
        "site:unieuro.it/online/Smartphone samsung galaxy iphone",
        "site:unieuro.it/online/Smartphone xiaomi oppo motorola",
        "site:unieuro.it/online/Smartphone 5g 128gb 256gb",
    ],
    "cuffie": [
        "site:unieuro.it/online/Cuffie-e-Auricolari cuffie auricolari",
        "site:unieuro.it/online/Cuffie-e-Auricolari auricolari bluetooth",
        "site:unieuro.it/online/Cuffie-e-Auricolari cuffie wireless sony jbl bose",
        "site:unieuro.it/online/Cuffie-e-Auricolari airpods earbuds true wireless",
    ],
    "laptop": [
        "site:unieuro.it/online/Notebook notebook laptop",
        "site:unieuro.it/online/Notebook hp lenovo asus acer",
        "site:unieuro.it/online/Notebook macbook laptop intel amd",
        "site:unieuro.it/online/Notebook 16gb 512gb ssd",
    ],
    "tv": [
        "site:unieuro.it/online/TV-DVD-e-Home-Cinema/TV smart tv televisore",
        "site:unieuro.it/online/TV-DVD-e-Home-Cinema/TV/Smart-TV smart tv",
        "site:unieuro.it/online/TV-Ultra-HD smart tv 4k",
        "site:unieuro.it/online/TV-QLED qled tv",
    ],
    "desktop": [
        "site:unieuro.it/online/PC-Desktop desktop pc computer",
        "site:unieuro.it/online/PC-Desktop hp lenovo desktop",
        "site:unieuro.it/online/Computer-e-Tablet/PC-Desktop-e-Monitor pc desktop",
        "site:unieuro.it/online/Computer-e-Tablet/Gaming pc gaming desktop",
    ],
    "casse_audio": [
        "site:unieuro.it/online/Audio-Ipod-e-Hi-Fi/Diffusori-Audio-Portatili/Diffusori-Bluetooth casse bluetooth speaker audio",
        "site:unieuro.it/online/Diffusori-Bluetooth jbl bose sony speaker",
        "site:unieuro.it/online/Diffusori-Bluetooth cassa bluetooth portatile",
        "site:unieuro.it/online/Audio-Ipod-e-Hi-Fi speaker diffusori bluetooth",
    ],
}


class FirecrawlBadRequestError(Exception):
    def __init__(self, endpoint, payload, body):
        self.endpoint = endpoint
        self.payload = payload
        self.body = body
        super().__init__(body)


# Utility comuni: normalizzazione testo e logging scarti con reason stabili.
def clean_text(value):
    if not value:
        return ""
    value = html_lib.unescape(str(value))
    value = value.replace("\\|", "|")
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


# Parsing prezzo: priorita a formato store-specific Unieuro, poi JSON-LD, poi fallback contestuale.
# La confidence resta alta solo per fonti strutturate/attese; regex contestuale affidabile resta media.
def parse_decimal_price(value):
    if value is None:
        return None

    value = clean_text(value)
    value = value.replace("€", "").replace("EUR", "")
    value = re.sub(r"[^\d,.]", "", value)

    if not value:
        return None

    if "," in value and "." in value:
        value = value.replace(".", "").replace(",", ".")
    else:
        value = value.replace(",", ".")

    try:
        price = float(value)
    except ValueError:
        return None

    if MIN_VALID_PRICE <= price <= MAX_VALID_PRICE:
        return price

    return None


def parse_store_product_line(text):
    if not text:
        return None

    normalized = html_lib.unescape(str(text)).replace("\\|", "|")
    pattern = re.compile(
        r"(?P<title>[^|\n]{4,250})\|(?P<sku>[A-Z0-9_+.-]{4,})\|"
        r"(?P<status>inStock|lowStock|outOfStock|preOrder|backOrder)\|"
        r"(?P<price>\d{1,4}(?:[,.]\d{1,2})?)\|",
        re.IGNORECASE,
    )

    match = None
    for line in normalized.splitlines():
        line = clean_text(line)
        match = pattern.search(line)
        if match:
            break

    if not match:
        return None

    price = parse_decimal_price(match.group("price"))

    if price is None:
        return None

    return {
        "title": clean_title(match.group("title")),
        "sku": clean_text(match.group("sku")),
        "availability": normalize_availability(match.group("status")),
        "price": price,
    }


def parse_price(text):
    if not text:
        return None, "bassa"

    product_line = parse_store_product_line(text)
    if product_line:
        return product_line["price"], "alta"

    json_price = extract_json_ld_price(text)
    if json_price is not None:
        return json_price, "alta"

    fallback_price = parse_contextual_euro_price(text)
    if fallback_price is not None:
        return fallback_price, "media"

    return None, "bassa"


def extract_euro_prices(value):
    matches = []
    matches.extend(re.findall(r"€\s*(\d{1,4}(?:[.,]\d{1,2})?)", value))
    matches.extend(re.findall(r"(\d{1,4}(?:[.,]\d{1,2})?)\s?€", value))

    prices = []
    for match in matches:
        price = parse_decimal_price(match)
        if price is not None:
            prices.append(price)

    return prices


def parse_contextual_euro_price(text):
    excluded_context = [
        "pagamenti",
        "interessi",
        "klarna",
        "paypal",
        "recensione",
        "ricevuto",
        "spedizione",
        "ritiro",
        "punti",
        "raee",
    ]

    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]

    for line in lines:
        lower = line.lower()
        if "iva inclusa" not in lower:
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


def parse_old_price(text, current_price=None):
    if not text:
        return None

    patterns = [
        r"Prezzo consigliato\s*(\d{1,4}(?:[.,]\d{1,2})?)",
        r"prezzo\s+consigliato\s*(\d{1,4}(?:[.,]\d{1,2})?)",
        r"anzich[eé]\s*€?\s*(\d{1,4}(?:[.,]\d{1,2})?)",
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


def firecrawl_post(endpoint, payload, attempt=1):
    try:
        response = requests.post(
            endpoint,
            headers=HEADERS,
            json=payload,
            timeout=FIRECRAWL_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException:
        if attempt <= FIRECRAWL_MAX_RETRIES:
            wait_seconds = 10 * attempt
            print(f"Errore rete Firecrawl. Ritento tra {wait_seconds} secondi...")
            time.sleep(wait_seconds)
            return firecrawl_post(endpoint, payload, attempt + 1)
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
    tokens = [token for token in query.split() if not token.startswith("site:")]

    if tokens:
        return f"site:unieuro.it/online {' '.join(tokens)}"

    return "site:unieuro.it/online unieuro prodotti"


def firecrawl_search(query, limit=10):
    safe_limit = min(max(int(limit), 1), FIRECRAWL_SEARCH_BATCH_LIMIT)
    payload = {
        "query": query,
        "limit": safe_limit,
        "sources": ["web"]
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
        "sources": ["web"]
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
        "formats": ["markdown", "html"]
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


# Discovery URL: canonicalizza link Unieuro, filtra solo product URL -pid... e amplia listing/categorie.
# Questo evita query Firecrawl troppo grandi e permette import progressivi senza crash.
def normalize_product_url(url):
    if not url:
        return None

    url = clean_text(url)

    if url.startswith("//"):
        url = f"https:{url}"

    if url.startswith("/"):
        url = f"{RETAILER_WEBSITE}{url}"

    parsed = urlsplit(url)

    if parsed.netloc.lower() not in {"www.unieuro.it", "unieuro.it"}:
        return None

    return urlunsplit((parsed.scheme or "https", parsed.netloc, parsed.path, "", ""))


def is_product_url(url):
    if not url:
        return False

    parsed = urlsplit(url)
    path = parsed.path

    if "/online/" not in path:
        return False

    return bool(re.search(r"-pid[A-Za-z0-9_+.-]+$", path))


def extract_product_code(url):
    if not url:
        return None

    match = re.search(r"-pid([A-Za-z0-9_+.-]+)$", urlsplit(url).path)
    if not match:
        return None

    return re.sub(r"[^a-z0-9]", "", match.group(1).lower())


def is_listing_url(url):
    if not url:
        return False

    parsed = urlsplit(url)
    path = parsed.path.lower()

    if "/online/" not in path:
        return False

    excluded_paths = [
        "/online/guida-",
        "/online/guida/",
        "/online/servizi",
        "/online/volantino",
        "/online/cart",
        "/online/login",
    ]

    if any(token in path for token in excluded_paths):
        return False

    return not is_product_url(url)


def extract_product_urls_from_listing_text(text):
    if not text:
        return []

    urls = []
    seen = set()
    pattern = r"(?:https?://(?:www\.)?unieuro\.it)?/online/[^\"'\s<>\)]*?-pid[A-Za-z0-9_+.-]+"

    for match in re.findall(pattern, text):
        url = normalize_product_url(match)

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


def add_product_candidate(candidates, seen_urls, url, search_title=None, search_description=None):
    url = normalize_product_url(url)

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


# Parsing titolo: usa raw line Unieuro, JSON-LD/H1 e metadata solo se non generici.
def clean_title(value):
    title = clean_text(value)

    if not title:
        return None

    title = re.sub(r"^\d+\s+su\s+\d+\s+del\s+prodotto\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^foto\s+\d+\s+su\s+\d+\s+del\s+prodotto\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^miniatura\s+prodotto\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\|\s*[^|]*in offerta su Unieuro\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*-\s*Unieuro\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\|\s*Cuffie e Auricolari.*$", "", title, flags=re.IGNORECASE)
    title = clean_text(title)

    generic_titles = {
        "dettagli",
        "servizi",
        "foto del prodotto",
        "foto prodotto",
        "miniatura prodotto",
        "unieuro",
        "unieuro: il miglior negozio di elettronica online",
    }

    if title.lower() in generic_titles:
        return None

    if len(title) < 4:
        return None

    return title


def get_metadata_value(metadata, *keys):
    for key in keys:
        value = metadata.get(key)
        if value:
            return value
    return None


def get_product_candidates_for_category(category_key, limit=10):
    if category_key not in CATEGORIES:
        raise ValueError(f"Categoria non supportata: {category_key}")

    candidates = []
    listing_urls = []
    seen_listing_urls = set()
    seen_urls = set()
    search_queries = CATEGORY_SEARCH_QUERIES.get(category_key, [CATEGORIES[category_key]])

    for query in search_queries:
        if len(candidates) >= limit:
            break

        batch_limit = min(limit - len(candidates), FIRECRAWL_SEARCH_BATCH_LIMIT)
        print(f"Search Firecrawl: limit={batch_limit} query={query}")

        results = firecrawl_search(query, limit=batch_limit)
        items = extract_items(results)

        for item in items:
            if not isinstance(item, dict):
                continue

            raw_url = item.get("url") or item.get("link") or ""
            url = normalize_product_url(raw_url)
            search_title = item.get("title")
            search_description = item.get("description") or item.get("snippet")

            if not url:
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
                if url not in seen_listing_urls:
                    listing_urls.append(url)
                    seen_listing_urls.add(url)
                continue

            log_discard("bad_url", raw_url, "Risultato search non prodotto")

    for listing_url in listing_urls:
        if len(candidates) >= limit:
            break

        try:
            product_urls = get_product_urls_from_listing(listing_url)
        except Exception as e:
            log_discard("scrape_error", listing_url, str(e))
            continue

        if not product_urls:
            log_discard("bad_url", listing_url, "Listing senza prodotti")
            continue

        for product_url in product_urls:
            add_product_candidate(candidates, seen_urls, product_url)

            if len(candidates) >= limit:
                break

    return candidates


def get_product_urls_for_category(category_key, limit=10):
    return [candidate["url"] for candidate in get_product_candidates_for_category(category_key, limit)]


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


def extract_json_ld_price(text):
    product = extract_json_ld_product(text)

    if not product:
        return None

    offers = product.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    if not isinstance(offers, dict):
        return None

    return parse_decimal_price(
        offers.get("price")
        or offers.get("lowPrice")
        or offers.get("highPrice")
        or offers.get("priceSpecification", {}).get("price")
    )


def extract_json_ld_title(text):
    product = extract_json_ld_product(text)
    if not product:
        return None

    return clean_title(product.get("name"))


def extract_heading_title(markdown):
    for line in markdown.splitlines():
        line = clean_text(line)

        if not line.startswith("# "):
            continue

        title = clean_title(line[2:])
        if title:
            return title

    return None


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


def normalize_availability(value):
    value = clean_text(value).lower()

    if not value:
        return "available"

    if "outofstock" in value or "out_of_stock" in value or "non disponibile" in value:
        return "out_of_stock"

    if "instock" in value or "lowstock" in value or "preorder" in value:
        return "available"

    if "in_stock" in value or "low_stock" in value or "disponibile" in value:
        return "available"

    return "available"


def extract_availability(text):
    product_line = parse_store_product_line(text)
    if product_line:
        return product_line["availability"]

    product = extract_json_ld_product(text)
    if product:
        offers = product.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        if isinstance(offers, dict):
            availability = normalize_availability(offers.get("availability"))
            if availability:
                return availability

    normalized = clean_text(text).lower()

    if "outofstock" in normalized or "non disponibile" in normalized:
        return "out_of_stock"

    return "available"


def extract_title_from_markdown(markdown, metadata=None, search_title=None):
    metadata = metadata or {}

    product_line = parse_store_product_line(markdown)
    if product_line and product_line.get("title"):
        return product_line["title"]

    for candidate in [
        extract_json_ld_title(markdown),
        extract_heading_title(markdown),
        get_metadata_value(metadata, "og:title", "title"),
        search_title,
    ]:
        title = clean_title(candidate)
        if title:
            return title

    lines = [clean_text(line) for line in markdown.splitlines() if clean_text(line)]

    for line in lines:
        lower = line.lower()

        if "|" in line and ("instock" in lower or "outofstock" in lower):
            title_part = line.split("|")[0]
            title_part = clean_title(title_part)

            if title_part:
                return title_part

    for line in lines:
        if line.startswith("!["):
            match = re.search(r"!\[(.*?)\]", line)
            if match:
                alt = clean_title(match.group(1))
                if alt:
                    return alt

    return None


def normalize_image_url(url):
    if not url:
        return None

    url = clean_text(url)

    if url.startswith("//"):
        return f"https:{url}"

    if url.startswith("/"):
        return f"{RETAILER_WEBSITE}{url}"

    if url.startswith("http://") or url.startswith("https://"):
        return url

    return None


def extract_image(html, markdown, metadata=None):
    metadata = metadata or {}

    for candidate in [
        get_metadata_value(metadata, "og:image", "image"),
        extract_json_ld_image(html),
        extract_json_ld_image(markdown),
    ]:
        image_url = normalize_image_url(candidate)
        if image_url:
            return image_url

    combined = f"{html}\n{markdown}"

    match = re.search(r'https://[^"\s\)]+?\.(?:jpg|jpeg|png|webp)', combined)

    if match:
        return match.group(0)

    return None


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

    final_url = normalize_product_url(metadata.get("url"))
    if final_url and not is_product_url(final_url):
        log_discard("bad_url", url, f"Firecrawl ha restituito {final_url}")
        return None

    final_code = extract_product_code(final_url)
    requested_code = extract_product_code(url)
    if final_code and requested_code and final_code != requested_code:
        log_discard("bad_url", url, f"Firecrawl ha restituito pid {final_code}")
        return None

    text = f"{markdown}\n{html}"

    title = extract_title_from_markdown(
        text,
        metadata=metadata,
        search_title=candidate.get("search_title"),
    )

    if not title:
        log_discard("no_title", url)
        return None

    price, confidence = parse_price(text)

    if price is None:
        log_discard("no_price", url, title)
        return None

    if confidence == "bassa":
        log_discard("low_confidence", url, title)
        return None

    availability = extract_availability(text)

    if availability == "out_of_stock":
        log_discard("out_of_stock", url, title)
        return None

    image_url = extract_image(html, markdown, metadata=metadata)
    old_price = parse_old_price(text, current_price=price)

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


# Import category loop: search batchata, scrape sequenziale, scarti loggati senza interrompere categoria.
def import_unieuro_category(category_key, limit=10):
    print(f"Import categoria Unieuro: {category_key}")

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

            # Salvataggio Supabase: tutte le scritture passano solo da save_product_offer().
            # Non fare insert diretti in products, product_offers o price_history dentro i collector.
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
                data_confidence=product["data_confidence"]
            )

            imported += 1
            print(f"Importato: {product['name']} - €{product['price']} - {product['data_confidence']}")

            time.sleep(2)

        except Exception as e:
            log_discard("scrape_error", url, str(e))

    print(f"\nImport completato. Prodotti importati: {imported}/{len(candidates)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "category",
        choices=CATEGORIES.keys(),
        help="Categoria da importare"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Numero massimo risultati da cercare"
    )

    args = parser.parse_args()

    import_unieuro_category(args.category, limit=args.limit)