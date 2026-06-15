import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.supabase_client import get_supabase_client


DEFAULT_PAGE_SIZE = 1000
DEFAULT_EXAMPLE_LIMIT = 8
MAX_CANDIDATE_EXAMPLES = 50

BRAND_TOKENS = {
    "acer", "amazon", "apple", "asus", "beats", "bose", "canon",
    "dyson", "garmin", "google", "hisense", "honor", "hp", "huawei",
    "jbl", "lenovo", "lg", "logitech", "microsoft", "motorola",
    "nintendo", "nothing", "oneplus", "oppo", "panasonic", "philips",
    "playstation", "realme", "samsung", "sennheiser", "sharp", "sony",
    "tcl", "xiaomi", "yamaha",
}

FAMILY_TOKENS = {
    "airpods", "bravia", "galaxy", "iphone", "ipad", "imac", "macbook",
    "pixel", "playstation", "ps5", "ps4", "switch", "watch", "xbox",
}

NOISE_WORDS = {
    "a", "ad", "al", "alla", "anche", "audio", "auricolari", "bluetooth",
    "cavo", "cellulare", "cm", "computer", "con", "cuffia", "cuffie",
    "da", "del", "della", "di", "e", "edition", "garanzia", "il", "in",
    "la", "le", "lo", "memoria", "new", "notebook", "nuovo", "offerta",
    "originale", "pc", "per", "portatile", "promo", "smart", "smartphone",
    "spedizione", "telefono", "televisore", "tv", "wireless",
}

IMPORTANT_VARIANTS = {
    "air", "classic", "digital", "disc", "edge", "lite", "max", "mini",
    "oled", "plus", "pro", "qled", "se", "slim", "ultra",
}

BUNDLE_TOKENS = {"bundle", "kit", "pack", "set"}
CONDITION_TOKENS = {"refurbished", "renewed", "ricondizionato", "usato"}

COLOR_TOKENS = {
    "argento", "azzurro", "beige", "bianco", "black", "blu", "blue",
    "grafite", "gray", "green", "grigio", "nero", "oro", "pink", "red",
    "rosa", "rosso", "silver", "verde", "white",
}

CAPACITY_RE = re.compile(r"\b(\d+(?:[,.]\d+)?)\s*(gb|tb)\b", re.IGNORECASE)
SCREEN_SIZE_RE = re.compile(
    r"\b(\d{1,3}(?:[,.]\d+)?)\s*(?:\"|”|″|'{1,2}|pollici|inch)",
    re.IGNORECASE,
)


def fetch_table_rows(table_name, page_size=DEFAULT_PAGE_SIZE, client=None):
    client = client or get_supabase_client()
    rows = []
    start = 0

    while True:
        response = (
            client.table(table_name)
            .select("*")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)

        if len(batch) < page_size:
            break

        start += page_size

    return rows


def fetch_snapshot(page_size=DEFAULT_PAGE_SIZE):
    return {
        "products": fetch_table_rows("products", page_size=page_size),
        "product_offers": fetch_table_rows("product_offers", page_size=page_size),
    }


def normalize_name(value):
    text = str(value or "").lower()
    text = CAPACITY_RE.sub(lambda match: f" {match.group(1)}{match.group(2)} ", text)
    text = SCREEN_SIZE_RE.sub(
        lambda match: f" {match.group(1).replace(',', '.')}inch ",
        text,
    )
    text = text.replace("playstation 5", "ps5")
    text = text.replace("usb-c", "usbc")
    text = text.replace("usb c", "usbc")
    text = re.sub(r"[^a-z0-9àèéìòù\s.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(value):
    normalized = normalize_name(value)
    return [
        token
        for token in normalized.split()
        if token and token not in NOISE_WORDS
    ]


def significant_name(product):
    return " ".join(tokenize(product.get("name")))


def infer_brand(tokens):
    for token in tokens:
        if token in BRAND_TOKENS:
            return token
    if "ps5" in tokens or "ps4" in tokens:
        return "sony"
    return None


def capacity_tokens(tokens):
    return {
        token.replace(",", ".")
        for token in tokens
        if re.fullmatch(r"\d+(?:[.]\d+)?(?:gb|tb)", token)
    }


def screen_size_tokens(tokens):
    return {
        token
        for token in tokens
        if re.fullmatch(r"\d{1,3}(?:[.]\d+)?inch", token)
    }


def screen_sizes_from_text(value):
    return {
        f"{match.group(1).replace(',', '.')}inch"
        for match in SCREEN_SIZE_RE.finditer(str(value or ""))
    }


def model_number_tokens(tokens):
    ignored = capacity_tokens(tokens) | screen_size_tokens(tokens)
    ignored.update({
        "5g", "4g", "4k", "8k", "dvbt2", "full", "hdr10", "hz", "mah",
        "main10", "s2", "uhd", "wi", "wifi",
    })
    return {
        token
        for token in tokens
        if any(char.isdigit() for char in token) and token not in ignored
    }


def family_tokens(tokens):
    found = {token for token in tokens if token in FAMILY_TOKENS}
    if "playstation" in tokens:
        found.add("playstation")
    return found


def product_features(product):
    raw_text = " ".join([
        str(product.get("name") or ""),
        str(product.get("search_keywords") or ""),
    ])
    tokens = tokenize(product.get("name"))
    search_tokens = tokenize(product.get("search_keywords"))
    all_tokens = list(dict.fromkeys([*tokens, *search_tokens]))

    return {
        "id": product.get("id"),
        "name": product.get("name") or "",
        "category": product.get("category") or "",
        "normalized_name": significant_name(product),
        "tokens": set(all_tokens),
        "name_tokens": set(tokens),
        "brand": infer_brand(all_tokens),
        "families": family_tokens(all_tokens),
        "model_numbers": model_number_tokens(all_tokens),
        "capacities": capacity_tokens(all_tokens),
        "screen_sizes": screen_size_tokens(all_tokens) | screen_sizes_from_text(raw_text),
        "variants": {token for token in all_tokens if token in IMPORTANT_VARIANTS},
        "colors": {token for token in all_tokens if token in COLOR_TOKENS},
        "bundle": bool(set(all_tokens) & BUNDLE_TOKENS),
        "condition_tokens": set(all_tokens) & CONDITION_TOKENS,
    }


def token_jaccard(left, right):
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def sequence_similarity(left, right):
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def differentiator_conflicts(left, right):
    conflicts = []

    if left["capacities"] and right["capacities"] and left["capacities"] != right["capacities"]:
        conflicts.append("different_capacity_storage")

    if left["screen_sizes"] and right["screen_sizes"] and left["screen_sizes"] != right["screen_sizes"]:
        conflicts.append("different_screen_size")

    if left["variants"] != right["variants"]:
        conflicts.append("different_variant")

    if left["bundle"] != right["bundle"]:
        conflicts.append("bundle_vs_standalone")

    if left["condition_tokens"] != right["condition_tokens"]:
        conflicts.append("different_condition")

    if (
        left["families"]
        and right["families"]
        and left["families"] == right["families"]
        and left["model_numbers"]
        and right["model_numbers"]
        and left["model_numbers"] != right["model_numbers"]
    ):
        conflicts.append("different_model_number")

    if left["colors"] and right["colors"] and left["colors"] != right["colors"]:
        conflicts.append("different_color")

    return conflicts


def has_blocking_conflict(conflicts):
    return any(conflict != "different_color" for conflict in conflicts)


def shared_identity_signal(left, right):
    if left["brand"] and right["brand"] and left["brand"] != right["brand"]:
        return False

    shared_family = bool(left["families"] & right["families"])
    shared_model_number = bool(left["model_numbers"] & right["model_numbers"])
    same_brand = bool(left["brand"] and left["brand"] == right["brand"])
    return shared_family or shared_model_number or same_brand


def candidate_for_pair(left, right, offer_summary=None):
    if left["category"] != right["category"]:
        return None

    exact_name = (
        left["normalized_name"]
        and left["normalized_name"] == right["normalized_name"]
    )
    jaccard = token_jaccard(left["tokens"], right["tokens"])
    similarity = sequence_similarity(left["normalized_name"], right["normalized_name"])
    identity_signal = shared_identity_signal(left, right)

    if not exact_name and not identity_signal:
        return None

    if not exact_name and jaccard < 0.42 and similarity < 0.74:
        return None

    conflicts = differentiator_conflicts(left, right)
    reasons = []

    if exact_name:
        reasons.append("exact normalized name")
    if left["brand"] and left["brand"] == right["brand"]:
        reasons.append(f"same brand: {left['brand']}")
    if left["families"] & right["families"]:
        reasons.append(
            "shared family: " + ", ".join(sorted(left["families"] & right["families"]))
        )
    if left["model_numbers"] & right["model_numbers"]:
        reasons.append(
            "shared model token: "
            + ", ".join(sorted(left["model_numbers"] & right["model_numbers"]))
        )

    confidence = "LOW"
    if has_blocking_conflict(conflicts):
        confidence = "LOW"
    elif "different_color" in conflicts:
        confidence = "MEDIUM"
    elif exact_name or (jaccard >= 0.80 and similarity >= 0.82):
        confidence = "HIGH"
    elif jaccard >= 0.55 or similarity >= 0.78:
        confidence = "MEDIUM"

    products = [
        candidate_product_summary(left, offer_summary),
        candidate_product_summary(right, offer_summary),
    ]

    return {
        "confidence": confidence,
        "category": left["category"],
        "products": products,
        "similarity": round(similarity, 3),
        "token_overlap": round(jaccard, 3),
        "reasons": reasons,
        "conflicts": conflicts,
        "warning": "candidate only - do not auto-merge",
    }


def candidate_product_summary(features, offer_summary=None):
    summary = (offer_summary or {}).get(features["id"], {})
    return {
        "id": features["id"],
        "name": short_name(features["name"]),
        "category": features["category"],
        "brand": features["brand"],
        "offer_count": summary.get("offer_count", 0),
        "store_count": summary.get("store_count", 0),
    }


def short_name(value, limit=120):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def offer_summary_by_product(offers):
    stores_by_product = defaultdict(set)
    offer_count_by_product = Counter()

    for offer in offers:
        product_id = offer.get("product_id")
        if not product_id:
            continue
        offer_count_by_product[product_id] += 1
        if offer.get("store_id"):
            stores_by_product[product_id].add(offer.get("store_id"))

    return {
        product_id: {
            "offer_count": offer_count_by_product[product_id],
            "store_count": len(stores_by_product[product_id]),
        }
        for product_id in offer_count_by_product
    }


def exact_duplicate_groups(features_by_id, offer_summary):
    groups = defaultdict(list)
    for features in features_by_id.values():
        key = (features["category"], features["normalized_name"])
        if all(key):
            groups[key].append(features)

    candidates = []
    for (category, _), items in groups.items():
        if len(items) < 2:
            continue
        candidates.append({
            "confidence": "HIGH",
            "category": category,
            "products": [
                candidate_product_summary(item, offer_summary)
                for item in items
            ],
            "similarity": 1.0,
            "token_overlap": 1.0,
            "reasons": ["exact normalized name"],
            "conflicts": [],
            "warning": "candidate only - do not auto-merge",
        })
    return candidates


def candidate_sort_key(candidate):
    confidence_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return (
        confidence_rank.get(candidate["confidence"], 3),
        -candidate["similarity"],
        -candidate["token_overlap"],
        candidate["category"],
        candidate["products"][0]["name"],
    )


def dedupe_candidates(candidates):
    seen = set()
    deduped = []
    for candidate in sorted(candidates, key=candidate_sort_key):
        ids = tuple(sorted(product["id"] for product in candidate["products"]))
        if ids in seen:
            continue
        seen.add(ids)
        deduped.append(candidate)
    return deduped


def find_candidate_groups(products, offers=None):
    offer_summary = offer_summary_by_product(offers or [])
    features_by_id = {
        product.get("id"): product_features(product)
        for product in products
        if product.get("id")
    }
    candidates = exact_duplicate_groups(features_by_id, offer_summary)

    by_category = defaultdict(list)
    for features in features_by_id.values():
        if features["category"]:
            by_category[features["category"]].append(features)

    exact_pairs = {
        tuple(sorted(product["id"] for product in candidate["products"]))
        for candidate in candidates
    }

    for category_products in by_category.values():
        for left, right in combinations(category_products, 2):
            pair_key = tuple(sorted([left["id"], right["id"]]))
            if pair_key in exact_pairs:
                continue
            candidate = candidate_for_pair(left, right, offer_summary)
            if candidate:
                candidates.append(candidate)

    return dedupe_candidates(candidates)


def build_summary(products, candidates):
    counts = Counter(candidate["confidence"] for candidate in candidates)
    exact_count = sum(
        1
        for candidate in candidates
        if "exact normalized name" in candidate["reasons"]
    )
    downgraded = sum(1 for candidate in candidates if candidate["conflicts"])
    categories = {
        product.get("category")
        for product in products
        if product.get("category")
    }

    return {
        "total_products_analyzed": len(products),
        "categories_analyzed": len(categories),
        "exact_normalized_duplicate_groups": exact_count,
        "high_confidence_candidate_groups": counts["HIGH"],
        "medium_confidence_candidate_groups": counts["MEDIUM"],
        "low_confidence_similar_groups": counts["LOW"],
        "groups_downgraded_due_to_differentiator_conflicts": downgraded,
        "candidate_groups_total": len(candidates),
        "warning": "Results are candidates only. Do not auto-merge.",
    }


def build_report(snapshot, example_limit=DEFAULT_EXAMPLE_LIMIT):
    products = snapshot.get("products", [])
    offers = snapshot.get("product_offers", [])
    candidates = find_candidate_groups(products, offers)
    return {
        "summary": build_summary(products, candidates),
        "examples": candidates[: max(0, example_limit)],
    }


def print_candidate(candidate):
    print(
        f"- [{candidate['confidence']}] {candidate['category']} "
        f"similarity={candidate['similarity']} overlap={candidate['token_overlap']}"
    )
    if candidate["reasons"]:
        print("  Reasons: " + "; ".join(candidate["reasons"]))
    if candidate["conflicts"]:
        print("  Differentiator conflicts: " + ", ".join(candidate["conflicts"]))
    for product in candidate["products"]:
        print(
            "  Product: "
            f"{product['id']} | {product['name']} "
            f"| offers={product['offer_count']} stores={product['store_count']}"
        )
    print("  Warning: candidate only - do not auto-merge")


def print_report(report):
    summary = report["summary"]
    print("# Spario Product Match Audit")
    print("WARNING: Results are candidates only. Do not auto-merge.\n")
    print("## Summary")
    print(f"- Total products analyzed: {summary['total_products_analyzed']}")
    print(f"- Categories analyzed: {summary['categories_analyzed']}")
    print(
        "- Exact normalized duplicate groups: "
        f"{summary['exact_normalized_duplicate_groups']}"
    )
    print(
        "- High-confidence candidate groups: "
        f"{summary['high_confidence_candidate_groups']}"
    )
    print(
        "- Medium-confidence candidate groups: "
        f"{summary['medium_confidence_candidate_groups']}"
    )
    print(
        "- Low-confidence similar groups: "
        f"{summary['low_confidence_similar_groups']}"
    )
    print(
        "- Groups downgraded due to differentiator conflicts: "
        f"{summary['groups_downgraded_due_to_differentiator_conflicts']}"
    )

    print("\n## Candidate Examples")
    if not report["examples"]:
        print("- No duplicate/equivalent candidates found by current rules.")
        return

    for candidate in report["examples"]:
        print_candidate(candidate)


def run_audit(page_size=DEFAULT_PAGE_SIZE, examples=DEFAULT_EXAMPLE_LIMIT):
    snapshot = fetch_snapshot(page_size=page_size)
    return build_report(snapshot, example_limit=min(examples, MAX_CANDIDATE_EXAMPLES))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read-only Spario product matching candidate audit."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of a readable console summary.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Rows to read per Supabase page.",
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=DEFAULT_EXAMPLE_LIMIT,
        help="Maximum candidate examples to print.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    report = run_audit(
        page_size=max(1, args.page_size),
        examples=max(0, args.examples),
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
