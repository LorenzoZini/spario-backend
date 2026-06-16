import argparse
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field


SEVERITY_OK = "OK"
SEVERITY_WARNING = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

TITLE_TOO_SHORT_CHARS = 8
TITLE_TOO_LONG_CHARS = 120

MVP_CATEGORY_KEYS = {
    "smartphone",
    "cuffie",
    "tv",
    "gaming",
    "gaming_accessori",
}

CAUTIOUS_CATEGORY_KEYS = {
    "laptop",
}

CATEGORY_ALIASES = {
    "smartphone": "smartphone",
    "smartphones": "smartphone",
    "telefono": "smartphone",
    "telefoni": "smartphone",
    "cellulare": "smartphone",
    "cellulari": "smartphone",
    "iphone": "smartphone",
    "samsung galaxy": "smartphone",
    "xiaomi": "smartphone",
    "cuffie": "cuffie",
    "cuffia": "cuffie",
    "auricolari": "cuffie",
    "auricolare": "cuffie",
    "headphones": "cuffie",
    "earbuds": "cuffie",
    "audio": "cuffie",
    "speaker": "cuffie",
    "casse": "cuffie",
    "casse_audio": "cuffie",
    "tv": "tv",
    "smart tv": "tv",
    "smart_tv": "tv",
    "televisore": "tv",
    "televisori": "tv",
    "home cinema": "tv",
    "gaming": "gaming",
    "console": "gaming",
    "ps5": "gaming",
    "ps4": "gaming",
    "playstation": "gaming",
    "xbox": "gaming",
    "nintendo": "gaming",
    "switch": "gaming",
    "controller": "gaming_accessori",
    "headset gaming": "gaming_accessori",
    "accessori gaming": "gaming_accessori",
    "gaming_accessori": "gaming_accessori",
    "dock": "gaming_accessori",
    "laptop": "laptop",
    "notebook": "laptop",
    "portatile": "laptop",
    "desktop": "laptop",
    "pc": "laptop",
    "computer": "laptop",
}

GENERIC_TITLE_TOKENS = {
    "accessorio",
    "audio",
    "auricolari",
    "bluetooth",
    "casse",
    "cellulare",
    "computer",
    "cuffie",
    "gaming",
    "laptop",
    "notebook",
    "pc",
    "prodotto",
    "smartphone",
    "speaker",
    "telefono",
    "televisore",
    "tv",
    "wireless",
}

RETAILER_NOISE_WORDS = {
    "black friday",
    "garanzia",
    "gratis",
    "nuovo",
    "offerta",
    "online",
    "promo",
    "promozione",
    "sconto",
    "spedizione",
}

BRAND_TOKENS = {
    "acer",
    "apple",
    "asus",
    "beats",
    "bose",
    "hp",
    "jbl",
    "lenovo",
    "lg",
    "microsoft",
    "motorola",
    "nintendo",
    "oppo",
    "philips",
    "samsung",
    "sony",
    "xiaomi",
}

MODEL_FAMILY_TOKENS = {
    "airpods",
    "bravia",
    "galaxy",
    "iphone",
    "ipad",
    "macbook",
    "playstation",
    "ps5",
    "switch",
    "xbox",
}

VARIANT_TOKENS = {
    "air",
    "classic",
    "digital",
    "disc",
    "edge",
    "lite",
    "max",
    "mini",
    "plus",
    "pro",
    "slim",
    "ultra",
}

CONDITION_OR_BUNDLE_TOKENS = {
    "bundle",
    "kit",
    "pack",
    "refurbished",
    "renewed",
    "ricondizionato",
    "usato",
}

COLOR_TOKENS = {
    "argento",
    "black",
    "blu",
    "blue",
    "grafite",
    "gray",
    "green",
    "grigio",
    "nero",
    "oro",
    "red",
    "rosa",
    "rosso",
    "silver",
    "verde",
    "white",
}

STORAGE_RE = re.compile(r"\b\d+(?:[,.]\d+)?\s*(?:gb|tb)\b", re.IGNORECASE)
SCREEN_SIZE_RE = re.compile(
    r"\b\d{1,3}(?:[,.]\d+)?\s*(?:\"|”|″|'{1,2}|pollici|inch)\b",
    re.IGNORECASE,
)


@dataclass
class TitleQuality:
    length: int
    token_count: int
    too_short: bool = False
    too_long: bool = False
    generic: bool = False
    retailer_noise_terms: list[str] = field(default_factory=list)
    important_differentiators: list[str] = field(default_factory=list)
    brand_tokens: list[str] = field(default_factory=list)
    model_tokens: list[str] = field(default_factory=list)


@dataclass
class QualityGateResult:
    accepted: bool
    severity: str
    confidence: str
    discard_reasons: list[str]
    warnings: list[str]
    normalized_category: str | None
    title_quality: dict
    matching_risk: str
    summary: str


def normalize_text(value):
    text = str(value or "").lower()
    text = text.replace("usb-c", "usbc")
    text = text.replace("usb c", "usbc")
    text = re.sub(r"[^a-z0-9àèéìòù\s,.\"'”″-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(value):
    return [
        token.strip(".,\"'”″-")
        for token in normalize_text(value).split()
        if token.strip(".,\"'”″-")
    ]


def first_present(candidate, *keys):
    for key in keys:
        value = candidate.get(key)
        if value not in (None, ""):
            return value
    return None


def parse_price(value):
    if value in (None, ""):
        return None

    if isinstance(value, str):
        value = value.strip().replace("€", "").replace(" ", "")
        if "," in value and "." in value:
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", ".")

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_category(candidate):
    category_value = normalize_text(
        first_present(candidate, "category", "category_key", "product_category")
    )

    if category_value in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[category_value]

    for alias, normalized in CATEGORY_ALIASES.items():
        if f" {alias} " in f" {category_value} ":
            return normalized

    return None


def detect_retailer_noise(normalized_title):
    return [
        term
        for term in sorted(RETAILER_NOISE_WORDS)
        if term in normalized_title
    ]


def detect_differentiators(title):
    normalized = normalize_text(title)
    tokens = set(tokenize(title))
    differentiators = set()

    differentiators.update(match.group(0).replace(" ", "").lower() for match in STORAGE_RE.finditer(title or ""))
    differentiators.update(match.group(0).lower() for match in SCREEN_SIZE_RE.finditer(title or ""))
    differentiators.update(tokens & VARIANT_TOKENS)
    differentiators.update(tokens & COLOR_TOKENS)
    differentiators.update(tokens & CONDITION_OR_BUNDLE_TOKENS)

    if "disc edition" in normalized:
        differentiators.add("disc_edition")
    if "digital edition" in normalized:
        differentiators.add("digital_edition")

    return sorted(differentiators)


def analyze_title(title):
    title = str(title or "").strip()
    normalized = normalize_text(title)
    tokens = tokenize(title)
    token_set = set(tokens)
    brand_tokens = sorted(token_set & BRAND_TOKENS)
    model_tokens = sorted(
        token
        for token in token_set
        if (
            token in MODEL_FAMILY_TOKENS
            or any(char.isdigit() for char in token)
        )
    )
    meaningful_tokens = [
        token
        for token in tokens
        if token not in GENERIC_TITLE_TOKENS and token not in RETAILER_NOISE_WORDS
    ]
    generic = (
        bool(tokens)
        and len(meaningful_tokens) <= 1
        and not brand_tokens
        and not model_tokens
    )

    return TitleQuality(
        length=len(title),
        token_count=len(tokens),
        too_short=len(title) < TITLE_TOO_SHORT_CHARS or len(tokens) < 2,
        too_long=len(title) > TITLE_TOO_LONG_CHARS,
        generic=generic,
        retailer_noise_terms=detect_retailer_noise(normalized),
        important_differentiators=detect_differentiators(title),
        brand_tokens=brand_tokens,
        model_tokens=model_tokens,
    )


def category_matching_complexity(normalized_category):
    if normalized_category in CAUTIOUS_CATEGORY_KEYS:
        return "high"

    if normalized_category in {"tv", "smartphone", "gaming", "gaming_accessori"}:
        return "medium"

    if normalized_category == "cuffie":
        return "medium"

    return "unknown"


def matching_risk_for(title_quality, normalized_category):
    if normalized_category in CAUTIOUS_CATEGORY_KEYS:
        return "high"

    if title_quality.generic:
        return "high"

    if title_quality.important_differentiators:
        return "medium"

    if not title_quality.brand_tokens and not title_quality.model_tokens:
        return "medium"

    return "low"


def stable_unique(values):
    return list(dict.fromkeys(values))


def evaluate_candidate(candidate, require_store=True):
    discard_reasons = []
    warnings = []

    name = first_present(candidate, "name", "title", "product_name")
    store = first_present(
        candidate,
        "store",
        "store_name",
        "store_id",
        "retailer",
        "source",
    )
    current_price_raw = first_present(
        candidate,
        "current_price",
        "price",
        "sale_price",
    )
    old_price_raw = first_present(candidate, "old_price", "list_price")
    url = first_present(candidate, "product_url", "url", "link")
    category = first_present(candidate, "category", "category_key", "product_category")
    image_url = first_present(candidate, "image_url", "image", "thumbnail")
    availability = first_present(candidate, "availability", "stock_status")

    current_price = parse_price(current_price_raw)
    old_price = parse_price(old_price_raw)

    if not name:
        discard_reasons.append("missing_name")

    if require_store and not store:
        discard_reasons.append("missing_store")

    if current_price_raw in (None, ""):
        discard_reasons.append("missing_price")
    elif current_price is None or current_price <= 0:
        discard_reasons.append("invalid_price")

    if not url:
        discard_reasons.append("missing_url")

    if not category:
        discard_reasons.append("missing_category")

    normalized_category = normalize_category(candidate)
    if category and not normalized_category:
        warnings.append("unknown_category")

    if old_price is not None and current_price is not None and old_price < current_price:
        warnings.append("old_price_lower_than_current_price")

    if not image_url:
        warnings.append("missing_image")

    if not availability:
        warnings.append("missing_availability")

    title_quality = analyze_title(name)

    if title_quality.too_short:
        warnings.append("title_too_short")

    if title_quality.too_long:
        warnings.append("title_too_long")

    if title_quality.generic:
        warnings.append("generic_title")

    if normalized_category in CAUTIOUS_CATEGORY_KEYS:
        warnings.append("category_high_matching_complexity")

    if title_quality.important_differentiators:
        warnings.append("important_differentiators_detected")

    if set(title_quality.important_differentiators) & CONDITION_OR_BUNDLE_TOKENS:
        warnings.append("possible_bundle_or_condition_variant")

    matching_risk = matching_risk_for(title_quality, normalized_category)
    if matching_risk in {"medium", "high"}:
        warnings.append("needs_matching_review")

    discard_reasons = stable_unique(discard_reasons)
    warnings = stable_unique(warnings)

    accepted = not discard_reasons
    if not accepted:
        severity = SEVERITY_CRITICAL
        confidence = CONFIDENCE_LOW
    elif warnings:
        severity = SEVERITY_WARNING
        confidence = confidence_for_warnings(warnings, matching_risk)
    else:
        severity = SEVERITY_OK
        confidence = CONFIDENCE_HIGH

    return QualityGateResult(
        accepted=accepted,
        severity=severity,
        confidence=confidence,
        discard_reasons=discard_reasons,
        warnings=warnings,
        normalized_category=normalized_category,
        title_quality=asdict(title_quality),
        matching_risk=matching_risk,
        summary=build_candidate_summary(
            accepted=accepted,
            severity=severity,
            normalized_category=normalized_category,
            discard_reasons=discard_reasons,
            warnings=warnings,
            matching_risk=matching_risk,
        ),
    )


def confidence_for_warnings(warnings, matching_risk):
    serious_warning_codes = {
        "generic_title",
        "unknown_category",
        "category_high_matching_complexity",
    }

    if matching_risk == "high" or serious_warning_codes & set(warnings):
        return CONFIDENCE_LOW

    return CONFIDENCE_MEDIUM


def build_candidate_summary(
    accepted,
    severity,
    normalized_category,
    discard_reasons,
    warnings,
    matching_risk,
):
    if not accepted:
        return (
            "Candidate rejected: critical fields failed "
            f"({', '.join(discard_reasons)})."
        )

    category_text = normalized_category or "unknown category"
    if severity == SEVERITY_OK:
        return f"Candidate accepted with high confidence for {category_text}."

    return (
        f"Candidate accepted with warnings for {category_text}; "
        f"matching risk is {matching_risk}."
    )


def summarize_quality_results(results, example_limit=5):
    total = len(results)
    accepted = [result for result in results if result.accepted]
    rejected = [result for result in results if not result.accepted]
    with_warnings = [
        result
        for result in accepted
        if result.warnings
    ]

    discard_counter = Counter(
        reason
        for result in results
        for reason in result.discard_reasons
    )
    warning_counter = Counter(
        warning
        for result in results
        for warning in result.warnings
    )
    category_counter = Counter(
        result.normalized_category or "unknown"
        for result in results
    )
    confidence_counter = Counter(result.confidence for result in results)

    return {
        "total_candidates": total,
        "accepted_candidates": len(accepted),
        "rejected_candidates": len(rejected),
        "candidates_with_warnings": len(with_warnings),
        "counts_by_discard_reason": dict(sorted(discard_counter.items())),
        "counts_by_warning": dict(sorted(warning_counter.items())),
        "counts_by_normalized_category": dict(sorted(category_counter.items())),
        "confidence_counts": dict(sorted(confidence_counter.items())),
        "average_confidence": average_confidence_label(confidence_counter, total),
        "examples": {
            "rejected": result_examples(rejected, example_limit),
            "warnings": result_examples(with_warnings, example_limit),
        },
        "summary": build_batch_summary(total, accepted, rejected, with_warnings),
    }


def average_confidence_label(confidence_counter, total):
    if total <= 0:
        return "none"

    score = (
        confidence_counter[CONFIDENCE_HIGH] * 3
        + confidence_counter[CONFIDENCE_MEDIUM] * 2
        + confidence_counter[CONFIDENCE_LOW]
    ) / total

    if score >= 2.5:
        return CONFIDENCE_HIGH

    if score >= 1.6:
        return CONFIDENCE_MEDIUM

    return CONFIDENCE_LOW


def result_examples(results, limit):
    examples = []
    for result in results[: max(0, limit)]:
        examples.append({
            "accepted": result.accepted,
            "severity": result.severity,
            "confidence": result.confidence,
            "discard_reasons": result.discard_reasons,
            "warnings": result.warnings,
            "normalized_category": result.normalized_category,
            "matching_risk": result.matching_risk,
            "summary": result.summary,
        })
    return examples


def build_batch_summary(total, accepted, rejected, with_warnings):
    if total == 0:
        return "No candidates provided for dry-run quality evaluation."

    return (
        f"Dry-run evaluated {total} candidates: {len(accepted)} accepted, "
        f"{len(rejected)} rejected, {len(with_warnings)} with warnings."
    )


def dry_run_quality_report(candidates, example_limit=5, require_store=True):
    results = [
        evaluate_candidate(candidate, require_store=require_store)
        for candidate in candidates
    ]
    return {
        "summary": summarize_quality_results(results, example_limit=example_limit),
        "results": [asdict(result) for result in results],
    }


def print_report(report):
    summary = report["summary"]
    print("# Spario Importer Quality Gates Dry Run")
    print(summary["summary"])
    print(f"- Total candidates: {summary['total_candidates']}")
    print(f"- Accepted: {summary['accepted_candidates']}")
    print(f"- Rejected: {summary['rejected_candidates']}")
    print(f"- With warnings: {summary['candidates_with_warnings']}")
    print(f"- Average confidence: {summary['average_confidence']}")
    print(f"- By category: {json.dumps(summary['counts_by_normalized_category'], ensure_ascii=False)}")
    print(f"- Discard reasons: {json.dumps(summary['counts_by_discard_reason'], ensure_ascii=False)}")
    print(f"- Warnings: {json.dumps(summary['counts_by_warning'], ensure_ascii=False)}")

    if summary["examples"]["rejected"]:
        print("\n## Rejected examples")
        for example in summary["examples"]["rejected"]:
            print(f"- {example['summary']}")

    if summary["examples"]["warnings"]:
        print("\n## Warning examples")
        for example in summary["examples"]["warnings"]:
            print(f"- {example['summary']} warnings={example['warnings']}")


def load_candidates_from_json(path):
    with open(path, "r", encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
        return payload["candidates"]

    if isinstance(payload, list):
        return payload

    raise ValueError("JSON must be a list or an object with a 'candidates' list.")


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only local dry-run quality gates for candidate importer records."
        )
    )
    parser.add_argument(
        "json_file",
        help="Local JSON file containing a list of candidate records.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full report as JSON.",
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=5,
        help="Maximum examples per issue group.",
    )
    parser.add_argument(
        "--store-optional",
        action="store_true",
        help="Do not reject candidates missing store identifiers.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    candidates = load_candidates_from_json(args.json_file)
    report = dry_run_quality_report(
        candidates,
        example_limit=max(0, args.examples),
        require_store=not args.store_optional,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
