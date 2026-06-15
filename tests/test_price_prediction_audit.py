import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

from scripts import price_prediction_audit


def product(product_id, name=None, category="tech"):
    return {
        "id": product_id,
        "name": name or f"Product {product_id}",
        "category": category,
    }


def history(row_id, product_id, price, store_id="s1", checked_at="2026-06-15T10:00:00+00:00"):
    return {
        "id": row_id,
        "product_id": product_id,
        "store_id": store_id,
        "price": price,
        "checked_at": checked_at,
        "condition": "new",
        "listing_type": "retail_online",
        "data_confidence": "alta",
    }


class PricePredictionAuditTests(unittest.TestCase):
    def sample_snapshot(self):
        rows = [
            history("h-p1-1", "p1", 100),
            history("h-p2-1", "p2", 200),
            history("h-p2-2", "p2", 200),
        ]
        rows.extend(
            history(f"h-p3-{index}", "p3", 40 + index)
            for index in range(4)
        )
        rows.extend(
            history(f"h-p4-{index}", "p4", 500 + index)
            for index in range(10)
        )
        rows.extend([
            history("h-orphan", "missing-product", 99),
            history("h-invalid", "p1", 0),
            {"id": "h-missing-product", "product_id": "", "price": 10},
            {"id": "h-missing-price", "product_id": "p1", "price": None},
        ])

        return {
            "products": [
                product("p0", "No History"),
                product("p1", "One Point"),
                product("p2", "Flat Price"),
                product("p3", "Weak Signal"),
                product("p4", "Strong Signal"),
            ],
            "product_offers": [
                {
                    "id": "o1",
                    "product_id": "p3",
                    "store_id": "s1",
                    "current_price": 99,
                },
                {
                    "id": "o2",
                    "product_id": "p4",
                    "store_id": "s1",
                    "current_price": 509,
                },
            ],
            "stores": [{"id": "s1", "name": "Store One"}],
            "price_history": rows,
        }

    def test_history_depth_classification_and_readiness_buckets(self):
        report = price_prediction_audit.build_report(self.sample_snapshot())

        self.assertEqual(
            report["coverage"]["depth_distribution"],
            {
                "insufficient_data": 2,
                "monitor_only": 1,
                "weak_buy_wait_guidance": 1,
                "stronger_buy_wait_guidance": 1,
            },
        )
        self.assertEqual(
            report["prediction_readiness"]["product_readiness_buckets"],
            report["coverage"]["depth_distribution"],
        )

    def test_products_with_no_history_are_reported(self):
        report = price_prediction_audit.build_report(self.sample_snapshot())
        metric = find_metric(
            report["coverage"],
            "Products without valid price history",
        )

        self.assertEqual(metric["count"], 1)
        self.assertEqual(metric["status"], "CRITICAL")

    def test_invalid_and_orphan_history_detection(self):
        report = price_prediction_audit.build_report(self.sample_snapshot())
        quality = report["quality"]

        self.assertEqual(
            find_metric(quality, "Price history rows with product_id not found in products")["count"],
            1,
        )
        self.assertEqual(
            find_metric(quality, "Price history rows missing product_id")["count"],
            1,
        )
        self.assertEqual(
            find_metric(quality, "Price history rows missing price")["count"],
            1,
        )
        self.assertEqual(
            find_metric(quality, "Price history rows with price <= 0")["count"],
            1,
        )

    def test_no_variation_and_repeated_prices_are_reported(self):
        report = price_prediction_audit.build_report(self.sample_snapshot())
        quality = report["quality"]

        self.assertEqual(
            find_metric(quality, "Repeated identical price points per product")["count"],
            1,
        )
        self.assertEqual(
            find_metric(quality, "Products with history but no price variation")["count"],
            1,
        )

    def test_current_offer_mismatch_is_reported(self):
        report = price_prediction_audit.build_report(self.sample_snapshot())
        metric = find_metric(
            report["quality"],
            "Current offer price differs from latest comparable history price",
        )

        self.assertEqual(metric["count"], 1)

    def test_recency_uses_timestamps_when_available(self):
        report = price_prediction_audit.build_report(
            self.sample_snapshot(),
            now=datetime(2026, 6, 16, tzinfo=timezone.utc),
        )
        recency = report["recency"]

        self.assertTrue(recency["timestamp_available"])
        self.assertEqual(
            find_metric(recency, "Products with history in last 3 days")["count"],
            4,
        )

    def test_summary_output_shape_is_stable(self):
        report = price_prediction_audit.build_report(self.sample_snapshot())

        output = io.StringIO()
        with redirect_stdout(output):
            price_prediction_audit.print_report(report)

        text = output.getvalue()
        self.assertIn("# Spario Price Prediction Readiness Audit", text)
        self.assertIn("## Price History Coverage", text)
        self.assertIn("## Recency", text)
        self.assertIn("## Quality", text)
        self.assertIn("## Prediction Readiness", text)
        self.assertIn("## Current Prediction Module Review", text)
        self.assertIn("## Top Risks", text)
        self.assertIn("## Recommended Next Actions", text)

    def test_json_output_shape_is_serializable(self):
        report = price_prediction_audit.build_report(self.sample_snapshot())
        payload = json.loads(json.dumps(report))

        self.assertEqual(
            set(payload),
            {
                "coverage",
                "recency",
                "quality",
                "prediction_readiness",
                "prediction_module_review",
                "top_risks",
                "recommended_next_actions",
            },
        )


def find_metric(section, label):
    for metric in section["metrics"]:
        if metric["label"] == label:
            return metric
    raise AssertionError(f"Metric not found: {label}")


if __name__ == "__main__":
    unittest.main()
