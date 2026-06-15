import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.supabase_client import get_supabase_client


TABLES = ("products", "product_offers", "stores", "price_history")
DEFAULT_PAGE_SIZE = 1000
DEFAULT_EXAMPLE_LIMIT = 5
RECENT_HISTORY_DAYS = 3
STALE_HISTORY_DAYS = 14
VALID_CONFIDENCE_VALUES = {"alta", "media"}

READINESS_BUCKETS = {
    "insufficient_data": (0, 1),
    "monitor_only": (2, 3),
    "weak_buy_wait_guidance": (4, 9),
    "stronger_buy_wait_guidance": (10, None),
}


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
        table_name: fetch_table_rows(table_name, page_size=page_size)
        for table_name in TABLES
    }


def parse_price(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed


def history_timestamp(row):
    return parse_datetime(row.get("checked_at") or row.get("created_at"))


def row_product_id(row):
    return row.get("product_id")


def is_history_usable(row):
    price = parse_price(row.get("price"))
    if price is None or price <= 0:
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


def issue(status, label, count=0, total=None, examples=None, note=None):
    return {
        "status": status,
        "label": label,
        "count": count,
        "total": total,
        "examples": examples or [],
        "note": note,
    }


def severity_for_count(count, critical=False):
    if count <= 0:
        return "OK"
    return "CRITICAL" if critical else "WARNING"


def product_label(product):
    name = str(product.get("name") or "").strip()
    category = str(product.get("category") or "").strip()
    product_id = str(product.get("id") or "").strip()
    label = name or product_id or "unknown product"
    if len(label) > 110:
        label = label[:107].rstrip() + "..."
    return f"{label} ({category})" if category else label


def history_label(row):
    parts = []
    if row.get("id"):
        parts.append(f"history={row.get('id')}")
    if row.get("product_id"):
        parts.append(f"product={row.get('product_id')}")
    if row.get("price") not in (None, ""):
        parts.append(f"price={row.get('price')}")
    return ", ".join(parts) or "unknown history row"


def sample_values(rows, formatter, limit):
    examples = []
    for row in rows:
        value = formatter(row)
        if value and value not in examples:
            examples.append(value)
        if len(examples) >= limit:
            break
    return examples


def valid_history_rows(history):
    return [row for row in history if is_history_usable(row)]


def group_history_by_product(history):
    grouped = defaultdict(list)
    for row in history:
        product_id = row.get("product_id")
        if product_id:
            grouped[product_id].append(row)
    return grouped


def group_history_by_product_store(history):
    grouped = defaultdict(list)
    for row in history:
        product_id = row.get("product_id")
        store_id = row.get("store_id")
        if product_id and store_id:
            grouped[(product_id, store_id)].append(row)
    return grouped


def classify_depth(count):
    for bucket, (minimum, maximum) in READINESS_BUCKETS.items():
        if count >= minimum and (maximum is None or count <= maximum):
            return bucket
    return "insufficient_data"


def sorted_prices(rows):
    sortable = []
    for index, row in enumerate(rows):
        price = parse_price(row.get("price"))
        if price is None:
            continue
        timestamp = history_timestamp(row) or datetime.min.replace(tzinfo=timezone.utc)
        sortable.append((timestamp, index, price, row))
    sortable.sort(key=lambda item: (item[0], item[1]))
    return sortable


def latest_history_price(rows):
    sortable = sorted_prices(rows)
    if not sortable:
        return None
    return sortable[-1][2]


def depth_distribution(depths):
    distribution = Counter(classify_depth(depth) for depth in depths)
    return {bucket: distribution[bucket] for bucket in READINESS_BUCKETS}


def audit_coverage(products, history, example_limit):
    product_by_id = {
        product.get("id"): product
        for product in products
        if product.get("id")
    }
    valid_history = valid_history_rows(history)
    history_by_product = group_history_by_product(valid_history)
    depths = [
        len(history_by_product.get(product_id, []))
        for product_id in product_by_id
    ]
    products_without_history = [
        product
        for product_id, product in product_by_id.items()
        if len(history_by_product.get(product_id, [])) == 0
    ]

    average_depth = round(statistics.mean(depths), 2) if depths else 0
    median_depth = statistics.median(depths) if depths else 0
    max_depth = max(depths) if depths else 0

    metrics = [
        issue("OK", "Total products", len(products)),
        issue("OK", "Total price history rows", len(history)),
        issue("OK", "Products with valid history", len(products) - len(products_without_history), len(products)),
        issue(
            severity_for_count(len(products_without_history), critical=True),
            "Products without valid price history",
            len(products_without_history),
            len(products),
            sample_values(products_without_history, product_label, example_limit),
        ),
        issue(
            "OK" if average_depth >= 4 else "WARNING",
            "Average valid history rows per product",
            average_depth,
            len(products),
            note="Conservative weak buy/wait guidance starts at 4 points.",
        ),
        issue("OK" if median_depth >= 4 else "WARNING", "Median valid history rows per product", median_depth, len(products)),
        issue("OK" if max_depth >= 10 else "WARNING", "Max valid history rows for one product", max_depth, len(products)),
        issue("OK", "Products with at least 2 valid history points", sum(1 for depth in depths if depth >= 2), len(products)),
        issue("OK", "Products with at least 3 valid history points", sum(1 for depth in depths if depth >= 3), len(products)),
        issue("OK", "Products with at least 5 valid history points", sum(1 for depth in depths if depth >= 5), len(products)),
        issue("OK", "Products with at least 10 valid history points", sum(1 for depth in depths if depth >= 10), len(products)),
    ]

    return {
        "metrics": metrics,
        "depth_distribution": depth_distribution(depths),
        "depths": depths,
        "valid_history_by_product": history_by_product,
    }


def audit_recency(products, history, example_limit, now=None):
    now = now or datetime.now(timezone.utc)
    product_by_id = {
        product.get("id"): product
        for product in products
        if product.get("id")
    }
    valid_history = valid_history_rows(history)
    timestamps = [
        timestamp
        for row in valid_history
        if (timestamp := history_timestamp(row))
    ]

    if not timestamps:
        return {
            "metrics": [
                issue(
                    "WARNING",
                    "History timestamps",
                    0,
                    len(history),
                    note="No usable checked_at/created_at timestamps found.",
                )
            ],
            "timestamp_available": False,
        }

    latest_by_product = {}
    for row in valid_history:
        product_id = row.get("product_id")
        timestamp = history_timestamp(row)
        if not product_id or not timestamp:
            continue
        if product_id not in latest_by_product or timestamp > latest_by_product[product_id]:
            latest_by_product[product_id] = timestamp

    recent_cutoff = now.timestamp() - (RECENT_HISTORY_DAYS * 24 * 60 * 60)
    stale_cutoff = now.timestamp() - (STALE_HISTORY_DAYS * 24 * 60 * 60)
    recent_products = [
        product_by_id[product_id]
        for product_id, timestamp in latest_by_product.items()
        if product_id in product_by_id and timestamp.timestamp() >= recent_cutoff
    ]
    stale_products = [
        product_by_id[product_id]
        for product_id, timestamp in latest_by_product.items()
        if product_id in product_by_id and timestamp.timestamp() < stale_cutoff
    ]

    metrics = [
        issue("OK", "Oldest valid history timestamp", min(timestamps).isoformat()),
        issue("OK", "Most recent valid history timestamp", max(timestamps).isoformat()),
        issue(
            "OK" if recent_products else "WARNING",
            f"Products with history in last {RECENT_HISTORY_DAYS} days",
            len(recent_products),
            len(products),
            sample_values(recent_products, product_label, example_limit),
        ),
        issue(
            severity_for_count(len(stale_products)),
            f"Products with stale history over {STALE_HISTORY_DAYS} days",
            len(stale_products),
            len(products),
            sample_values(stale_products, product_label, example_limit),
        ),
    ]

    return {
        "metrics": metrics,
        "timestamp_available": True,
    }


def audit_quality(products, offers, history, example_limit):
    product_ids = {
        product.get("id")
        for product in products
        if product.get("id")
    }
    products_by_id = {
        product.get("id"): product
        for product in products
        if product.get("id")
    }
    valid_history = valid_history_rows(history)
    valid_history_by_product = group_history_by_product(valid_history)
    valid_history_by_product_store = group_history_by_product_store(valid_history)

    missing_product_id = [row for row in history if not row.get("product_id")]
    orphan_history = [
        row
        for row in history
        if row.get("product_id") and row.get("product_id") not in product_ids
    ]
    missing_price = [row for row in history if row.get("price") in (None, "")]
    invalid_price = [
        row
        for row in history
        if parse_price(row.get("price")) is not None and parse_price(row.get("price")) <= 0
    ]
    repeated_identical = repeated_identical_price_points(valid_history_by_product)
    no_variation_products = products_with_no_variation(
        valid_history_by_product,
        products_by_id,
    )
    current_offer_mismatches = offer_latest_history_mismatches(
        offers,
        valid_history_by_product_store,
    )

    metrics = [
        issue(
            severity_for_count(len(missing_product_id), critical=True),
            "Price history rows missing product_id",
            len(missing_product_id),
            len(history),
            sample_values(missing_product_id, history_label, example_limit),
        ),
        issue(
            severity_for_count(len(orphan_history), critical=True),
            "Price history rows with product_id not found in products",
            len(orphan_history),
            len(history),
            sample_values(orphan_history, history_label, example_limit),
        ),
        issue(
            severity_for_count(len(missing_price), critical=True),
            "Price history rows missing price",
            len(missing_price),
            len(history),
            sample_values(missing_price, history_label, example_limit),
        ),
        issue(
            severity_for_count(len(invalid_price), critical=True),
            "Price history rows with price <= 0",
            len(invalid_price),
            len(history),
            sample_values(invalid_price, history_label, example_limit),
        ),
        issue(
            severity_for_count(repeated_identical["total_repeated_points"]),
            "Repeated identical price points per product",
            repeated_identical["total_repeated_points"],
            len(history),
            repeated_identical["examples"][:example_limit],
            note="Repeated prices can be normal, but too many duplicates add little prediction signal.",
        ),
        issue(
            severity_for_count(len(no_variation_products)),
            "Products with history but no price variation",
            len(no_variation_products),
            len(products),
            sample_values(no_variation_products, product_label, example_limit),
            note="No variation means the assistant should prefer monitoring language.",
        ),
        issue(
            severity_for_count(len(current_offer_mismatches)),
            "Current offer price differs from latest comparable history price",
            len(current_offer_mismatches),
            len(offers),
            current_offer_mismatches[:example_limit],
            note="Comparable means same product_id + store_id.",
        ),
    ]

    return {
        "metrics": metrics,
        "valid_history_by_product": valid_history_by_product,
        "valid_history_by_product_store": valid_history_by_product_store,
    }


def repeated_identical_price_points(history_by_product):
    total = 0
    examples = []

    for product_id, rows in history_by_product.items():
        prices = [parse_price(row.get("price")) for row in rows]
        prices = [price for price in prices if price is not None]
        duplicates = len(prices) - len(set(prices))
        if duplicates <= 0:
            continue
        total += duplicates
        examples.append(f"product={product_id}: {duplicates} repeated points")

    return {"total_repeated_points": total, "examples": examples}


def products_with_no_variation(history_by_product, products_by_id):
    products = []
    for product_id, rows in history_by_product.items():
        prices = [parse_price(row.get("price")) for row in rows]
        prices = [price for price in prices if price is not None]
        if len(prices) >= 2 and len(set(prices)) == 1 and product_id in products_by_id:
            products.append(products_by_id[product_id])
    return products


def offer_latest_history_mismatches(offers, history_by_product_store):
    mismatches = []
    for offer in offers:
        product_id = offer.get("product_id")
        store_id = offer.get("store_id")
        current_price = parse_price(offer.get("current_price"))
        if not product_id or not store_id or current_price is None:
            continue

        latest_price = latest_history_price(
            history_by_product_store.get((product_id, store_id), [])
        )
        if latest_price is None:
            continue

        if abs(current_price - latest_price) > 0.01:
            mismatches.append(
                f"product={product_id}, store={store_id}: "
                f"current={round(current_price, 2)}, latest_history={round(latest_price, 2)}"
            )
    return mismatches


def audit_prediction_readiness(products, offers, valid_history_by_product, valid_history_by_product_store):
    product_ids = [
        product.get("id")
        for product in products
        if product.get("id")
    ]
    product_depths = {
        product_id: len(valid_history_by_product.get(product_id, []))
        for product_id in product_ids
    }
    product_bucket_counts = Counter(
        classify_depth(depth)
        for depth in product_depths.values()
    )

    offer_store_depths = []
    for offer in offers:
        product_id = offer.get("product_id")
        store_id = offer.get("store_id")
        if not product_id or not store_id:
            continue
        offer_store_depths.append(
            len(valid_history_by_product_store.get((product_id, store_id), []))
        )
    offer_store_bucket_counts = Counter(
        classify_depth(depth)
        for depth in offer_store_depths
    )

    metrics = [
        readiness_issue(
            "Products with insufficient data",
            product_bucket_counts["insufficient_data"],
            len(product_ids),
            "CRITICAL" if product_bucket_counts["insufficient_data"] else "OK",
        ),
        readiness_issue(
            "Products ready for monitor-only guidance",
            product_bucket_counts["monitor_only"],
            len(product_ids),
            "OK",
        ),
        readiness_issue(
            "Products with weak buy/wait signal",
            product_bucket_counts["weak_buy_wait_guidance"],
            len(product_ids),
            "OK",
        ),
        readiness_issue(
            "Products with stronger buy/wait signal",
            product_bucket_counts["stronger_buy_wait_guidance"],
            len(product_ids),
            "OK" if product_bucket_counts["stronger_buy_wait_guidance"] else "WARNING",
        ),
        issue(
            "WARNING" if offer_store_bucket_counts["insufficient_data"] else "OK",
            "Current offer-store pairs with insufficient predictor history",
            offer_store_bucket_counts["insufficient_data"],
            len(offer_store_depths),
            note=(
                "Current predictor groups history by product_id + store_id, "
                "so this is stricter than product-level readiness."
            ),
        ),
    ]

    return {
        "metrics": metrics,
        "product_readiness_buckets": {
            bucket: product_bucket_counts[bucket]
            for bucket in READINESS_BUCKETS
        },
        "offer_store_readiness_buckets": {
            bucket: offer_store_bucket_counts[bucket]
            for bucket in READINESS_BUCKETS
        },
    }


def readiness_issue(label, count, total, status):
    return issue(
        status,
        label,
        count,
        total,
        note=(
            "Thresholds: 0-1 insufficient, 2-3 monitor-only, "
            "4-9 weak signal, 10+ stronger signal."
        ),
    )


def prediction_module_review():
    return {
        "metrics": [
            issue(
                "OK",
                "Prediction decisions currently supported",
                "insufficient_data, buy_now, wait, monitor",
            ),
            issue(
                "WARNING",
                "Default minimum valid history points",
                3,
                note=(
                    "This is enough for a basic signal, but not enough for "
                    "strong UX claims."
                ),
            ),
            issue(
                "OK",
                "Data expected by module",
                "products, product_offers, stores, price_history",
            ),
            issue(
                "OK",
                "Supabase access",
                "read-only selects through centralized client",
            ),
            issue("OK", "Database writes", 0, note="No write path is used by the predictor."),
            issue(
                "OK",
                "Assistant integration",
                "Used for when_to_buy after best offer + store-level history lookup",
            ),
            issue(
                "WARNING",
                "Before heavy UX exposure",
                "increase history depth and disclose confidence",
            ),
        ]
    }


def build_top_risks(report):
    risks = []
    for section_name in (
        "coverage",
        "recency",
        "quality",
        "prediction_readiness",
        "prediction_module_review",
    ):
        for metric in report[section_name]["metrics"]:
            if metric["status"] in {"CRITICAL", "WARNING"}:
                risks.append({
                    "status": metric["status"],
                    "section": section_name,
                    "label": metric["label"],
                    "count": metric["count"],
                })

    risks.sort(key=lambda item: (item["status"] != "CRITICAL", -numeric_count(item)))
    return risks[:8]


def numeric_count(item):
    count = item.get("count")
    return count if isinstance(count, (int, float)) else 0


def recommended_actions(report):
    readiness = report["prediction_readiness"]["product_readiness_buckets"]
    actions = [
        "Continue collecting scheduled price snapshots before strong buy/wait UX.",
        "Prefer monitor/alert wording when products have fewer than 4 history points.",
        "Prioritize history depth for products with multiple retailer offers.",
    ]
    if readiness["stronger_buy_wait_guidance"] == 0:
        actions.append("Do not market prediction accuracy yet: no product has 10+ points.")
    if report["quality"]["metrics"][-1]["count"]:
        actions.append("Investigate offers whose current price differs from latest store history.")
    return actions


def build_report(snapshot, example_limit=DEFAULT_EXAMPLE_LIMIT, now=None):
    products = snapshot.get("products", [])
    offers = snapshot.get("product_offers", [])
    history = snapshot.get("price_history", [])

    coverage = audit_coverage(products, history, example_limit)
    recency = audit_recency(products, history, example_limit, now=now)
    quality = audit_quality(products, offers, history, example_limit)
    readiness = audit_prediction_readiness(
        products,
        offers,
        quality["valid_history_by_product"],
        quality["valid_history_by_product_store"],
    )

    report = {
        "coverage": {
            "metrics": coverage["metrics"],
            "depth_distribution": coverage["depth_distribution"],
        },
        "recency": recency,
        "quality": {
            "metrics": quality["metrics"],
        },
        "prediction_readiness": readiness,
        "prediction_module_review": prediction_module_review(),
    }
    report["top_risks"] = build_top_risks(report)
    report["recommended_next_actions"] = recommended_actions(report)
    return report


def print_metric(metric):
    total = metric.get("total")
    count = metric.get("count")
    suffix = f" / {total}" if total is not None else ""
    print(f"- [{metric['status']}] {metric['label']}: {count}{suffix}")
    if metric.get("note"):
        print(f"  Note: {metric['note']}")
    for example in metric.get("examples", []):
        print(f"  Example: {example}")


def print_section(title, section):
    print(f"\n## {title}")
    for metric in section["metrics"]:
        print_metric(metric)


def print_report(report):
    print("# Spario Price Prediction Readiness Audit")
    print("WARNING: Readiness only. This does not claim prediction accuracy.")
    print_section("Price History Coverage", report["coverage"])
    print("\n### History depth distribution")
    for bucket, count in report["coverage"]["depth_distribution"].items():
        print(f"- {bucket}: {count}")

    print_section("Recency", report["recency"])
    print_section("Quality", report["quality"])
    print_section("Prediction Readiness", report["prediction_readiness"])
    print("\n### Offer-store readiness buckets")
    for bucket, count in report["prediction_readiness"]["offer_store_readiness_buckets"].items():
        print(f"- {bucket}: {count}")

    print_section("Current Prediction Module Review", report["prediction_module_review"])

    print("\n## Top Risks")
    if not report["top_risks"]:
        print("- [OK] No major readiness risks found.")
    else:
        for risk in report["top_risks"]:
            print(
                f"- [{risk['status']}] {risk['section']}: "
                f"{risk['label']} ({risk['count']})"
            )

    print("\n## Recommended Next Actions")
    for action in report["recommended_next_actions"]:
        print(f"- {action}")


def run_audit(page_size=DEFAULT_PAGE_SIZE, examples=DEFAULT_EXAMPLE_LIMIT):
    snapshot = fetch_snapshot(page_size=page_size)
    return build_report(snapshot, example_limit=examples)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read-only Spario price prediction readiness audit."
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
        help="Maximum examples to print per issue.",
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
