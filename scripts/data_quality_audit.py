import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.supabase_client import get_supabase_client


TABLES = ("products", "product_offers", "stores", "price_history")
DEFAULT_PAGE_SIZE = 1000
DEFAULT_EXAMPLE_LIMIT = 5
LONG_PRODUCT_NAME_LENGTH = 120


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


def fetch_catalog_snapshot(page_size=DEFAULT_PAGE_SIZE):
    return {
        table_name: fetch_table_rows(table_name, page_size=page_size)
        for table_name in TABLES
    }


def normalize_text(value):
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9àèéìòù\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalized_product_key(product):
    return (
        normalize_text(product.get("category")),
        normalize_text(product.get("name")),
    )


def parse_number(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def observed_columns(rows):
    columns = set()
    for row in rows:
        columns.update(row.keys())
    return columns


def has_column(rows, column_name):
    return column_name in observed_columns(rows)


def is_missing(row, column_name):
    return row.get(column_name) in (None, "")


def sample_values(rows, formatter, limit):
    examples = []
    for row in rows:
        value = formatter(row)
        if value and value not in examples:
            examples.append(value)
        if len(examples) >= limit:
            break
    return examples


def product_label(product):
    name = str(product.get("name") or "").strip()
    category = str(product.get("category") or "").strip()
    product_id = str(product.get("id") or "").strip()

    if name and category:
        return f"{name} ({category})"
    return name or product_id or "unknown product"


def store_label(store):
    return str(store.get("name") or store.get("id") or "unknown store").strip()


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


def duplicate_groups(rows, key_func):
    groups = defaultdict(list)
    for row in rows:
        key = key_func(row)
        if all(key):
            groups[key].append(row)
    return {
        key: values
        for key, values in groups.items()
        if len(values) > 1
    }


def audit_products(products, offers, history, example_limit):
    product_ids = {
        product.get("id")
        for product in products
        if product.get("id")
    }
    offer_product_ids = {
        offer.get("product_id")
        for offer in offers
        if offer.get("product_id")
    }
    history_product_ids = {
        row.get("product_id")
        for row in history
        if row.get("product_id")
    }

    duplicate_names = duplicate_groups(products, normalized_product_key)
    long_name_products = [
        product
        for product in products
        if len(str(product.get("name") or "")) > LONG_PRODUCT_NAME_LENGTH
    ]
    products_without_offers = [
        product
        for product in products
        if product.get("id") not in offer_product_ids
    ]
    products_without_history = [
        product
        for product in products
        if product.get("id") not in history_product_ids
    ]

    metrics = [
        issue("OK", "Total products", len(products)),
        field_missing_issue(
            products,
            "name",
            "Products missing name",
            example_limit,
            product_label,
            critical=True,
        ),
        field_missing_issue(
            products,
            "category",
            "Products missing category",
            example_limit,
            product_label,
            critical=True,
        ),
        optional_field_missing_issue(
            products,
            "canonical_key",
            "Products missing canonical_key",
            example_limit,
            product_label,
        ),
        optional_field_missing_issue(
            products,
            "search_keywords",
            "Products missing search_keywords",
            example_limit,
            product_label,
        ),
        optional_field_missing_issue(
            products,
            "image_url",
            "Products missing image_url",
            example_limit,
            product_label,
        ),
        issue(
            severity_for_count(len(long_name_products)),
            f"Products with names over {LONG_PRODUCT_NAME_LENGTH} chars",
            len(long_name_products),
            len(products),
            sample_values(long_name_products, product_label, example_limit),
        ),
        issue(
            severity_for_count(len(duplicate_names)),
            "Duplicate/suspicious products by normalized name + category",
            len(duplicate_names),
            len(products),
            duplicate_examples(duplicate_names, example_limit),
        ),
        issue(
            severity_for_count(len(products_without_offers), critical=True),
            "Products with no linked offers",
            len(products_without_offers),
            len(products),
            sample_values(products_without_offers, product_label, example_limit),
        ),
        issue(
            severity_for_count(len(products_without_history)),
            "Products with no price history",
            len(products_without_history),
            len(products),
            sample_values(products_without_history, product_label, example_limit),
        ),
    ]

    return {
        "total": len(products),
        "product_ids": product_ids,
        "metrics": metrics,
    }


def audit_offers(products, offers, stores, example_limit):
    product_ids = {
        product.get("id")
        for product in products
        if product.get("id")
    }
    store_ids = {
        store.get("id")
        for store in stores
        if store.get("id")
    }

    missing_product_id = [
        offer for offer in offers if is_missing(offer, "product_id")
    ]
    orphan_product_id = [
        offer
        for offer in offers
        if offer.get("product_id") and offer.get("product_id") not in product_ids
    ]
    missing_store_id = [
        offer for offer in offers if is_missing(offer, "store_id")
    ]
    orphan_store_id = [
        offer
        for offer in offers
        if offer.get("store_id") and offer.get("store_id") not in store_ids
    ]
    missing_current_price = [
        offer for offer in offers if is_missing(offer, "current_price")
    ]
    invalid_current_price = [
        offer
        for offer in offers
        if (
            parse_number(offer.get("current_price")) is not None
            and parse_number(offer.get("current_price")) <= 0
        )
    ]
    old_price_lower = [
        offer
        for offer in offers
        if old_price_is_lower_than_current(offer)
    ]
    products_with_multiple_offers = {
        product_id: count
        for product_id, count in Counter(
            offer.get("product_id")
            for offer in offers
            if offer.get("product_id")
        ).items()
        if count > 1
    }
    duplicate_offer_groups = duplicate_groups(
        offers,
        lambda offer: (
            str(offer.get("product_id") or "").strip(),
            str(offer.get("store_id") or "").strip(),
            str(offer.get("product_url") or "").strip(),
        ),
    )

    metrics = [
        issue("OK", "Total offers", len(offers)),
        issue(
            severity_for_count(len(missing_product_id), critical=True),
            "Offers missing product_id",
            len(missing_product_id),
            len(offers),
            sample_values(missing_product_id, offer_label, example_limit),
        ),
        issue(
            severity_for_count(len(orphan_product_id), critical=True),
            "Offers with product_id not found in products",
            len(orphan_product_id),
            len(offers),
            sample_values(orphan_product_id, offer_label, example_limit),
        ),
        issue(
            severity_for_count(len(missing_store_id), critical=True),
            "Offers missing store_id",
            len(missing_store_id),
            len(offers),
            sample_values(missing_store_id, offer_label, example_limit),
        ),
        issue(
            severity_for_count(len(orphan_store_id), critical=True),
            "Offers with store_id not found in stores",
            len(orphan_store_id),
            len(offers),
            sample_values(orphan_store_id, offer_label, example_limit),
        ),
        issue(
            severity_for_count(len(missing_current_price), critical=True),
            "Offers missing current_price",
            len(missing_current_price),
            len(offers),
            sample_values(missing_current_price, offer_label, example_limit),
        ),
        issue(
            severity_for_count(len(invalid_current_price), critical=True),
            "Offers with current_price <= 0",
            len(invalid_current_price),
            len(offers),
            sample_values(invalid_current_price, offer_label, example_limit),
        ),
        issue(
            severity_for_count(len(old_price_lower)),
            "Offers where old_price is lower than current_price",
            len(old_price_lower),
            len(offers),
            sample_values(old_price_lower, offer_label, example_limit),
        ),
        optional_field_missing_issue(
            offers,
            "product_url",
            "Offers missing product_url",
            example_limit,
            offer_label,
        ),
        optional_field_missing_issue(
            offers,
            "availability",
            "Offers missing availability",
            example_limit,
            offer_label,
        ),
        issue(
            severity_for_count(len(duplicate_offer_groups)),
            "Duplicate offers by product/store/url",
            len(duplicate_offer_groups),
            len(offers),
            duplicate_examples(duplicate_offer_groups, example_limit),
        ),
        issue(
            "OK" if products_with_multiple_offers else "WARNING",
            "Products with multiple offers",
            len(products_with_multiple_offers),
            len(product_ids),
            [
                f"{product_id}: {count} offers"
                for product_id, count in list(
                    products_with_multiple_offers.items()
                )[:example_limit]
            ],
            note=(
                "Useful for comparison. Warning only if this remains zero as "
                "the catalog grows."
            ),
        ),
    ]

    return {
        "total": len(offers),
        "metrics": metrics,
        "orphan_product_offers": len(orphan_product_id),
        "orphan_store_offers": len(orphan_store_id),
        "products_with_multiple_offers": len(products_with_multiple_offers),
    }


def audit_stores(stores, offers, example_limit):
    offer_store_ids = {
        offer.get("store_id")
        for offer in offers
        if offer.get("store_id")
    }
    stores_without_offers = [
        store
        for store in stores
        if store.get("id") not in offer_store_ids
    ]
    duplicate_names = duplicate_groups(
        stores,
        lambda store: (normalize_text(store.get("name")),),
    )

    metrics = [
        issue("OK", "Total stores", len(stores)),
        field_missing_issue(
            stores,
            "name",
            "Stores missing name",
            example_limit,
            store_label,
            critical=True,
        ),
        issue(
            severity_for_count(len(duplicate_names)),
            "Stores with duplicate names",
            len(duplicate_names),
            len(stores),
            duplicate_examples(duplicate_names, example_limit),
        ),
        issue(
            severity_for_count(len(stores_without_offers)),
            "Stores with no linked offers",
            len(stores_without_offers),
            len(stores),
            sample_values(stores_without_offers, store_label, example_limit),
        ),
    ]

    return {
        "total": len(stores),
        "metrics": metrics,
    }


def audit_price_history(products, history, example_limit):
    product_ids = {
        product.get("id")
        for product in products
        if product.get("id")
    }
    history_by_product = Counter(
        row.get("product_id")
        for row in history
        if row.get("product_id")
    )
    products_with_history = {
        product_id
        for product_id in history_by_product
        if product_id in product_ids
    }
    products_without_history = [
        product
        for product in products
        if product.get("id") not in products_with_history
    ]
    missing_product_id = [
        row for row in history if is_missing(row, "product_id")
    ]
    orphan_product_id = [
        row
        for row in history
        if row.get("product_id") and row.get("product_id") not in product_ids
    ]
    missing_price = [
        row for row in history if is_missing(row, "price")
    ]
    invalid_price = [
        row
        for row in history
        if (
            parse_number(row.get("price")) is not None
            and parse_number(row.get("price")) <= 0
        )
    ]
    average_points = (
        round(sum(history_by_product.values()) / len(products_with_history), 2)
        if products_with_history
        else 0
    )

    metrics = [
        issue("OK", "Total price history rows", len(history)),
        issue(
            severity_for_count(len(missing_product_id), critical=True),
            "Price history rows missing product_id",
            len(missing_product_id),
            len(history),
            sample_values(missing_product_id, history_label, example_limit),
        ),
        issue(
            severity_for_count(len(orphan_product_id), critical=True),
            "Price history rows with product_id not found in products",
            len(orphan_product_id),
            len(history),
            sample_values(orphan_product_id, history_label, example_limit),
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
        issue("OK", "Products with price history", len(products_with_history), len(products)),
        issue(
            severity_for_count(len(products_without_history)),
            "Products without price history",
            len(products_without_history),
            len(products),
            sample_values(products_without_history, product_label, example_limit),
        ),
        issue(
            "OK" if average_points >= 2 else "WARNING",
            "Average history points per product with history",
            average_points,
            len(products_with_history),
            note=(
                "Reliable buy/wait guidance improves when each product has "
                "multiple history points."
            ),
        ),
    ]

    return {
        "total": len(history),
        "metrics": metrics,
        "products_with_history": len(products_with_history),
        "products_without_history": len(products_without_history),
        "average_points_per_product_with_history": average_points,
        "orphan_history_rows": len(orphan_product_id),
    }


def old_price_is_lower_than_current(offer):
    current_price = parse_number(offer.get("current_price"))
    old_price = parse_number(offer.get("old_price"))
    return (
        current_price is not None
        and old_price is not None
        and old_price < current_price
    )


def offer_label(offer):
    offer_id = str(offer.get("id") or "").strip()
    product_id = str(offer.get("product_id") or "").strip()
    store_id = str(offer.get("store_id") or "").strip()
    price = offer.get("current_price")
    parts = []
    if offer_id:
        parts.append(f"offer={offer_id}")
    if product_id:
        parts.append(f"product={product_id}")
    if store_id:
        parts.append(f"store={store_id}")
    if price not in (None, ""):
        parts.append(f"price={price}")
    return ", ".join(parts) or "unknown offer"


def history_label(row):
    row_id = str(row.get("id") or "").strip()
    product_id = str(row.get("product_id") or "").strip()
    price = row.get("price")
    parts = []
    if row_id:
        parts.append(f"history={row_id}")
    if product_id:
        parts.append(f"product={product_id}")
    if price not in (None, ""):
        parts.append(f"price={price}")
    return ", ".join(parts) or "unknown history row"


def field_missing_issue(rows, column, label, example_limit, formatter, critical=False):
    missing = [row for row in rows if is_missing(row, column)]
    return issue(
        severity_for_count(len(missing), critical=critical),
        label,
        len(missing),
        len(rows),
        sample_values(missing, formatter, example_limit),
    )


def optional_field_missing_issue(rows, column, label, example_limit, formatter):
    if not has_column(rows, column):
        return issue(
            "OK",
            label,
            0,
            len(rows),
            note=f"Skipped: column '{column}' was not present in fetched rows.",
        )

    return field_missing_issue(
        rows,
        column,
        label,
        example_limit,
        formatter,
    )


def duplicate_examples(groups, limit):
    examples = []
    for key, values in groups.items():
        key_text = " / ".join(str(part) for part in key if part)
        examples.append(f"{key_text}: {len(values)} rows")
        if len(examples) >= limit:
            break
    return examples


def build_cross_table_metrics(products_audit, offers_audit, history_audit):
    metrics = [
        issue(
            severity_for_count(
                offers_audit["orphan_product_offers"],
                critical=True,
            ),
            "Offer rows referencing missing products",
            offers_audit["orphan_product_offers"],
        ),
        issue(
            severity_for_count(
                offers_audit["orphan_store_offers"],
                critical=True,
            ),
            "Offer rows referencing missing stores",
            offers_audit["orphan_store_offers"],
        ),
        issue(
            severity_for_count(
                history_audit["orphan_history_rows"],
                critical=True,
            ),
            "Price history rows referencing missing products",
            history_audit["orphan_history_rows"],
        ),
        issue(
            "OK" if offers_audit["products_with_multiple_offers"] else "WARNING",
            "Products with retailer comparison data",
            offers_audit["products_with_multiple_offers"],
            products_audit["total"],
            note=(
                "Spario becomes more useful when important products have "
                "offers from multiple stores."
            ),
        ),
    ]
    return {"metrics": metrics}


def build_top_risks(report):
    candidates = []
    for section_name in (
        "products",
        "offers",
        "stores",
        "price_history",
        "cross_table_integrity",
    ):
        for metric in report[section_name]["metrics"]:
            if metric["status"] in {"CRITICAL", "WARNING"}:
                candidates.append({
                    "status": metric["status"],
                    "section": section_name,
                    "label": metric["label"],
                    "count": metric["count"],
                })

    candidates.sort(key=lambda item: (item["status"] != "CRITICAL", -safe_count(item)))
    return candidates[:8]


def safe_count(item):
    count = item.get("count")
    return count if isinstance(count, (int, float)) else 0


def audit_snapshot(snapshot, example_limit=DEFAULT_EXAMPLE_LIMIT):
    products = snapshot.get("products", [])
    offers = snapshot.get("product_offers", [])
    stores = snapshot.get("stores", [])
    history = snapshot.get("price_history", [])

    products_audit = audit_products(products, offers, history, example_limit)
    offers_audit = audit_offers(products, offers, stores, example_limit)
    stores_audit = audit_stores(stores, offers, example_limit)
    history_audit = audit_price_history(products, history, example_limit)

    report = {
        "products": products_audit,
        "offers": offers_audit,
        "stores": stores_audit,
        "price_history": history_audit,
        "cross_table_integrity": build_cross_table_metrics(
            products_audit,
            offers_audit,
            history_audit,
        ),
    }
    report["top_risks"] = build_top_risks(report)
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
    print("# Spario Data Quality Audit")
    print_section("Products", report["products"])
    print_section("Offers", report["offers"])
    print_section("Stores", report["stores"])
    print_section("Price History", report["price_history"])
    print_section("Cross-table integrity", report["cross_table_integrity"])

    print("\n## Top risks / recommended next actions")
    if not report["top_risks"]:
        print("- [OK] No critical catalog health risks found.")
        return

    for risk in report["top_risks"]:
        print(
            f"- [{risk['status']}] {risk['section']}: "
            f"{risk['label']} ({risk['count']})"
        )


def run_audit(page_size=DEFAULT_PAGE_SIZE, example_limit=DEFAULT_EXAMPLE_LIMIT):
    snapshot = fetch_catalog_snapshot(page_size=page_size)
    return audit_snapshot(snapshot, example_limit=example_limit)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read-only Spario Supabase catalog data quality audit."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the audit report as JSON instead of a console summary.",
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
        example_limit=max(0, args.examples),
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
