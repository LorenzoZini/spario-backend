import argparse
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from core.supabase_client import get_supabase_client


VALID_CONFIDENCE_VALUES = {"alta", "media"}
DEFAULT_MIN_HISTORY_POINTS = 3

PRODUCT_COLUMNS = "id,name,category"
OFFER_COLUMNS = (
    "id,product_id,store_id,current_price,availability,condition,"
    "listing_type,data_confidence"
)
HISTORY_COLUMNS = (
    "id,product_id,store_id,price,checked_at,condition,"
    "listing_type,data_confidence"
)
STORE_COLUMNS = "id,name"

supabase = get_supabase_client()


@dataclass
class PricePrediction:
    product_id: str
    product_name: str
    category: str | None
    store_id: str
    store_name: str
    current_price: float | None
    recommendation: str
    confidence: str
    reason: str
    history_points: int
    history_min: float | None
    history_max: float | None
    history_avg: float | None
    recent_avg: float | None
    trend: str
    volatility_pct: float | None
    data_quality: str


def parse_price(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_datetime(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)

    if isinstance(value, datetime):
        return value

    text = str(value).replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed


def round_money(value):
    if value is None:
        return None

    return round(float(value), 2)


def round_pct(value):
    if value is None:
        return None

    return round(float(value), 2)


def is_usable_row(row, include_low_confidence=False):
    confidence = row.get("data_confidence")

    if not include_low_confidence and confidence and confidence not in VALID_CONFIDENCE_VALUES:
        return False

    condition = row.get("condition")
    if condition and condition != "new":
        return False

    listing_type = row.get("listing_type")
    if listing_type and listing_type != "retail_online":
        return False

    return parse_price(row.get("price")) is not None


def fetch_table(table_name, columns):
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


def load_dataset():
    return {
        "products": fetch_table("products", PRODUCT_COLUMNS),
        "offers": fetch_table("product_offers", OFFER_COLUMNS),
        "history": fetch_table("price_history", HISTORY_COLUMNS),
        "stores": fetch_table("stores", STORE_COLUMNS),
    }


def build_history_index(history_rows, include_low_confidence=False):
    index = {}

    for row in history_rows:
        if not is_usable_row(row, include_low_confidence=include_low_confidence):
            continue

        key = (row.get("product_id"), row.get("store_id"))
        index.setdefault(key, []).append(row)

    for rows in index.values():
        rows.sort(key=lambda item: parse_datetime(item.get("checked_at") or item.get("created_at")))

    return index


def get_trend(prices):
    if len(prices) < 2:
        return "unknown"

    first = prices[0]
    last = prices[-1]

    if first <= 0:
        return "unknown"

    change_pct = ((last - first) / first) * 100

    if change_pct <= -3:
        return "falling"

    if change_pct >= 3:
        return "rising"

    return "stable"


def get_volatility_pct(prices):
    if len(prices) < 2:
        return None

    avg_price = statistics.mean(prices)

    if avg_price <= 0:
        return None

    return (statistics.pstdev(prices) / avg_price) * 100


def get_data_quality(history_rows, min_history_points):
    count = len(history_rows)

    if count < min_history_points:
        return "insufficient"

    high_confidence = sum(1 for row in history_rows if row.get("data_confidence") == "alta")

    if count >= 8 and high_confidence / count >= 0.5:
        return "strong"

    if count >= min_history_points:
        return "usable"

    return "limited"


def confidence_from_quality(data_quality, history_points):
    if data_quality == "strong":
        return "alta"

    if data_quality == "usable":
        return "media"

    if history_points > 0:
        return "bassa"

    return "bassa"


def make_insufficient_prediction(product, offer, store_name, reason, history_points=0):
    return PricePrediction(
        product_id=product.get("id"),
        product_name=product.get("name") or "Prodotto senza nome",
        category=product.get("category"),
        store_id=offer.get("store_id"),
        store_name=store_name,
        current_price=round_money(parse_price(offer.get("current_price"))),
        recommendation="insufficient_data",
        confidence="bassa",
        reason=reason,
        history_points=history_points,
        history_min=None,
        history_max=None,
        history_avg=None,
        recent_avg=None,
        trend="unknown",
        volatility_pct=None,
        data_quality="insufficient",
    )


def predict_offer(product, offer, store_name, history_rows, min_history_points):
    current_price = parse_price(offer.get("current_price"))

    if current_price is None:
        return make_insufficient_prediction(
            product,
            offer,
            store_name,
            "Prezzo corrente mancante.",
            history_points=len(history_rows),
        )

    availability = (offer.get("availability") or "").lower()
    if availability == "out_of_stock":
        return make_insufficient_prediction(
            product,
            offer,
            store_name,
            "Offerta attualmente non disponibile.",
            history_points=len(history_rows),
        )

    if len(history_rows) < min_history_points:
        return make_insufficient_prediction(
            product,
            offer,
            store_name,
            f"Storico insufficiente: {len(history_rows)}/{min_history_points} punti validi.",
            history_points=len(history_rows),
        )

    prices = [parse_price(row.get("price")) for row in history_rows]
    prices = [price for price in prices if price is not None]

    if len(prices) < min_history_points:
        return make_insufficient_prediction(
            product,
            offer,
            store_name,
            f"Storico prezzi insufficiente: {len(prices)}/{min_history_points} prezzi validi.",
            history_points=len(prices),
        )

    history_min = min(prices)
    history_max = max(prices)
    history_avg = statistics.mean(prices)
    recent_prices = prices[-min(3, len(prices)) :]
    recent_avg = statistics.mean(recent_prices)
    trend = get_trend(prices)
    volatility_pct = get_volatility_pct(prices)
    data_quality = get_data_quality(history_rows, min_history_points)
    confidence = confidence_from_quality(data_quality, len(prices))

    near_low = current_price <= history_min * 1.03
    below_avg = current_price <= history_avg * 0.92
    above_avg = current_price >= history_avg * 1.08
    far_from_low = current_price >= history_min * 1.15

    if near_low or below_avg:
        recommendation = "buy_now"
        reason = "Prezzo corrente vicino al minimo storico o sotto la media storica."
    elif above_avg and far_from_low:
        recommendation = "wait"
        reason = "Prezzo corrente sopra la media e lontano dal minimo storico."
    elif trend == "falling" and current_price > recent_avg:
        recommendation = "wait"
        reason = "Trend recente in calo: conviene monitorare prima di comprare."
    else:
        recommendation = "monitor"
        reason = "Prezzo non estremo rispetto allo storico disponibile."

    return PricePrediction(
        product_id=product.get("id"),
        product_name=product.get("name") or "Prodotto senza nome",
        category=product.get("category"),
        store_id=offer.get("store_id"),
        store_name=store_name,
        current_price=round_money(current_price),
        recommendation=recommendation,
        confidence=confidence,
        reason=reason,
        history_points=len(prices),
        history_min=round_money(history_min),
        history_max=round_money(history_max),
        history_avg=round_money(history_avg),
        recent_avg=round_money(recent_avg),
        trend=trend,
        volatility_pct=round_pct(volatility_pct),
        data_quality=data_quality,
    )


def predict_prices(
    product_id=None,
    category=None,
    limit=20,
    include_low_confidence=False,
    min_history_points=DEFAULT_MIN_HISTORY_POINTS,
):
    dataset = load_dataset()

    products_by_id = {
        product.get("id"): product
        for product in dataset["products"]
        if product.get("id")
    }
    stores_by_id = {
        store.get("id"): store.get("name") or "Store sconosciuto"
        for store in dataset["stores"]
        if store.get("id")
    }
    history_index = build_history_index(
        dataset["history"],
        include_low_confidence=include_low_confidence,
    )

    predictions = []

    for offer in dataset["offers"]:
        product = products_by_id.get(offer.get("product_id"))
        if not product:
            continue

        if product_id and product.get("id") != product_id:
            continue

        if category and product.get("category") != category:
            continue

        store_name = stores_by_id.get(offer.get("store_id"), "Store sconosciuto")
        history_rows = history_index.get((product.get("id"), offer.get("store_id")), [])
        prediction = predict_offer(
            product=product,
            offer=offer,
            store_name=store_name,
            history_rows=history_rows,
            min_history_points=min_history_points,
        )
        predictions.append(prediction)

        if len(predictions) >= limit:
            break

    return predictions


def prediction_to_dict(prediction):
    return asdict(prediction)


def format_table(predictions):
    if not predictions:
        return "Nessuna previsione disponibile."

    headers = [
        "recommendation",
        "confidence",
        "price",
        "hist",
        "trend",
        "store",
        "product",
    ]
    rows = []

    for prediction in predictions:
        rows.append(
            [
                prediction.recommendation,
                prediction.confidence,
                f"€{prediction.current_price:.2f}" if prediction.current_price is not None else "-",
                str(prediction.history_points),
                prediction.trend,
                prediction.store_name,
                prediction.product_name[:60],
            ]
        )

    widths = [
        max(len(str(row[index])) for row in [headers, *rows])
        for index in range(len(headers))
    ]

    lines = [
        " | ".join(str(value).ljust(widths[index]) for index, value in enumerate(headers)),
        "-+-".join("-" * width for width in widths),
    ]

    for row in rows:
        lines.append(
            " | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))
        )

    return "\n".join(lines)


def run_insufficient_history_self_test():
    product = {
        "id": "test-product",
        "name": "Prodotto Test",
        "category": "tech",
    }
    offer = {
        "store_id": "test-store",
        "current_price": 199.99,
        "availability": "available",
    }
    prediction = predict_offer(
        product=product,
        offer=offer,
        store_name="Store Test",
        history_rows=[],
        min_history_points=DEFAULT_MIN_HISTORY_POINTS,
    )
    return [prediction]


def build_parser():
    parser = argparse.ArgumentParser(
        description="Motore read-only di price prediction per Spario."
    )

    parser.add_argument("--product-id", default=None, help="Filtra per product id")
    parser.add_argument("--category", default=None, help="Filtra per categoria prodotto")
    parser.add_argument("--limit", type=int, default=20, help="Numero massimo previsioni")
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Formato output",
    )
    parser.add_argument(
        "--include-low-confidence",
        action="store_true",
        help="Include anche storico con data_confidence bassa",
    )
    parser.add_argument(
        "--min-history-points",
        type=int,
        default=DEFAULT_MIN_HISTORY_POINTS,
        help="Numero minimo di punti storico per una previsione utile",
    )
    parser.add_argument(
        "--self-test-insufficient-history",
        action="store_true",
        help="Esegue un test locale senza Supabase per storico insufficiente",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.limit <= 0:
        parser.error("--limit deve essere maggiore di zero")

    if args.min_history_points <= 0:
        parser.error("--min-history-points deve essere maggiore di zero")

    try:
        if args.self_test_insufficient_history:
            predictions = run_insufficient_history_self_test()
        else:
            predictions = predict_prices(
                product_id=args.product_id,
                category=args.category,
                limit=args.limit,
                include_low_confidence=args.include_low_confidence,
                min_history_points=args.min_history_points,
            )
    except Exception as exc:
        print(f"ERRORE prediction detail={exc}")
        return 1

    if args.format == "json":
        print(
            json.dumps(
                [prediction_to_dict(prediction) for prediction in predictions],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(format_table(predictions))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
