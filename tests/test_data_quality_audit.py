import io
import unittest
from contextlib import redirect_stdout

from scripts import data_quality_audit


def metric(section, label):
    for item in section["metrics"]:
        if item["label"] == label:
            return item
    raise AssertionError(f"Metric not found: {label}")


class DataQualityAuditTests(unittest.TestCase):
    def sample_snapshot(self):
        return {
            "products": [
                {
                    "id": "p1",
                    "name": "AirPods Max",
                    "category": "cuffie",
                    "canonical_key": "airpods-max",
                    "search_keywords": "airpods max",
                    "image_url": "https://example.test/image.jpg",
                },
                {
                    "id": "p2",
                    "name": "AirPods Max",
                    "category": "cuffie",
                    "canonical_key": "",
                    "search_keywords": "",
                    "image_url": "",
                },
                {
                    "id": "p3",
                    "name": "",
                    "category": "tech",
                    "canonical_key": "missing-name",
                    "search_keywords": "missing name",
                    "image_url": None,
                },
                {
                    "id": "p4",
                    "name": "Xbox Series X",
                    "category": "",
                    "canonical_key": "xbox-series-x",
                    "search_keywords": "xbox series x",
                    "image_url": "https://example.test/xbox.jpg",
                },
            ],
            "product_offers": [
                {
                    "id": "o1",
                    "product_id": "p1",
                    "store_id": "s1",
                    "current_price": 0,
                    "old_price": 100,
                    "product_url": "https://example.test/p1",
                    "availability": "available",
                },
                {
                    "id": "o2",
                    "product_id": "missing-product",
                    "store_id": "s1",
                    "current_price": 20,
                    "old_price": 10,
                    "product_url": "",
                    "availability": "",
                },
                {
                    "id": "o3",
                    "product_id": "p2",
                    "store_id": "missing-store",
                    "current_price": 50,
                    "old_price": 80,
                    "product_url": "https://example.test/p2",
                    "availability": "available",
                },
                {
                    "id": "o4",
                    "product_id": "p2",
                    "store_id": "missing-store",
                    "current_price": 45,
                    "old_price": 90,
                    "product_url": "https://example.test/p2",
                    "availability": "available",
                },
                {
                    "id": "o5",
                    "product_id": "",
                    "store_id": "",
                    "current_price": None,
                    "old_price": None,
                    "product_url": "",
                    "availability": None,
                },
            ],
            "stores": [
                {"id": "s1", "name": "Unieuro"},
                {"id": "s2", "name": "Unieuro"},
                {"id": "s3", "name": ""},
            ],
            "price_history": [
                {"id": "h1", "product_id": "p1", "price": 100},
                {"id": "h2", "product_id": "missing-product", "price": 90},
                {"id": "h3", "product_id": "p2", "price": 0},
                {"id": "h4", "product_id": "", "price": None},
            ],
        }

    def test_detects_missing_product_fields_and_duplicates(self):
        report = data_quality_audit.audit_snapshot(self.sample_snapshot())

        products = report["products"]
        self.assertEqual(
            metric(products, "Products missing name")["count"],
            1,
        )
        self.assertEqual(
            metric(products, "Products missing category")["count"],
            1,
        )
        self.assertEqual(
            metric(products, "Products missing canonical_key")["count"],
            1,
        )
        self.assertEqual(
            metric(products, "Products missing search_keywords")["count"],
            1,
        )
        self.assertEqual(
            metric(products, "Products missing image_url")["count"],
            2,
        )
        self.assertEqual(
            metric(
                products,
                "Duplicate/suspicious products by normalized name + category",
            )["count"],
            1,
        )

    def test_detects_invalid_prices_and_orphan_offers(self):
        report = data_quality_audit.audit_snapshot(self.sample_snapshot())
        offers = report["offers"]

        self.assertEqual(metric(offers, "Offers missing product_id")["count"], 1)
        self.assertEqual(
            metric(offers, "Offers with product_id not found in products")["count"],
            1,
        )
        self.assertEqual(metric(offers, "Offers missing store_id")["count"], 1)
        self.assertEqual(
            metric(offers, "Offers with store_id not found in stores")["count"],
            2,
        )
        self.assertEqual(
            metric(offers, "Offers missing current_price")["count"],
            1,
        )
        self.assertEqual(
            metric(offers, "Offers with current_price <= 0")["count"],
            1,
        )
        self.assertEqual(
            metric(
                offers,
                "Offers where old_price is lower than current_price",
            )["count"],
            1,
        )

    def test_detects_products_without_offers_and_history(self):
        report = data_quality_audit.audit_snapshot(self.sample_snapshot())

        self.assertEqual(
            metric(report["products"], "Products with no linked offers")["count"],
            2,
        )
        self.assertEqual(
            metric(report["products"], "Products with no price history")["count"],
            2,
        )

    def test_detects_store_and_price_history_issues(self):
        report = data_quality_audit.audit_snapshot(self.sample_snapshot())

        self.assertEqual(
            metric(report["stores"], "Stores missing name")["count"],
            1,
        )
        self.assertEqual(
            metric(report["stores"], "Stores with duplicate names")["count"],
            1,
        )
        self.assertEqual(
            metric(
                report["price_history"],
                "Price history rows missing product_id",
            )["count"],
            1,
        )
        self.assertEqual(
            metric(
                report["price_history"],
                "Price history rows with product_id not found in products",
            )["count"],
            1,
        )
        self.assertEqual(
            metric(
                report["price_history"],
                "Price history rows with price <= 0",
            )["count"],
            1,
        )

    def test_output_summary_shape_is_stable(self):
        report = data_quality_audit.audit_snapshot(self.sample_snapshot())

        output = io.StringIO()
        with redirect_stdout(output):
            data_quality_audit.print_report(report)

        text = output.getvalue()
        self.assertIn("# Spario Data Quality Audit", text)
        self.assertIn("## Products", text)
        self.assertIn("## Offers", text)
        self.assertIn("## Stores", text)
        self.assertIn("## Price History", text)
        self.assertIn("## Cross-table integrity", text)
        self.assertIn("## Top risks / recommended next actions", text)


if __name__ == "__main__":
    unittest.main()
