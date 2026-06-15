import json
import os
import unittest
from unittest.mock import patch


os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

from ai import shopping_assistant
from core import retrieval_diagnostics


def product(product_id, name, category):
    return {
        "id": product_id,
        "name": name,
        "category": category,
        "image_url": None,
        "search_keywords": name,
    }


def offer(product_id, store_id, price):
    return {
        "id": f"offer-{product_id}",
        "product_id": product_id,
        "store_id": store_id,
        "current_price": price,
        "old_price": None,
        "product_url": f"https://store.test/{product_id}",
        "availability": "available",
        "condition": "new",
        "listing_type": "retail_online",
        "data_confidence": "alta",
    }


def parse_log(record):
    prefix = "retrieval_summary "
    message = record.getMessage()
    if not message.startswith(prefix):
        raise AssertionError(f"Unexpected diagnostic log: {message}")
    return json.loads(message[len(prefix):])


class RetrievalDiagnosticsTests(unittest.TestCase):
    def test_disabled_diagnostics_do_not_emit_logs(self):
        with (
            patch(
                "core.retrieval_diagnostics.get_retrieval_diagnostics_enabled",
                return_value=False,
            ),
            patch.object(
                retrieval_diagnostics.logger,
                "info",
            ) as mock_log,
        ):
            token = retrieval_diagnostics.start_retrieval_diagnostics()
            retrieval_diagnostics.record_bounded_candidates(10, True)
            retrieval_diagnostics.finish_retrieval_diagnostics(
                token,
                succeeded=True,
            )

        self.assertIsNone(token)
        mock_log.assert_not_called()

    def test_enabled_diagnostics_emit_one_structured_summary(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="category_recommendation",
            query="tv",
            normalized_question="tv",
            category="tv",
            keywords=("tv",),
        )
        products = [
            product(f"tv-{index}", f"TV Product {index}", "tv")
            for index in range(1, 21)
        ]
        offers = [
            offer(item["id"], "store-1", 300 + index)
            for index, item in enumerate(products)
        ]

        with (
            patch(
                "core.retrieval_diagnostics.get_retrieval_diagnostics_enabled",
                return_value=True,
            ),
            patch(
                "ai.shopping_assistant.parse_question",
                return_value=parsed,
            ),
            patch(
                "ai.shopping_assistant.fetch_candidate_products",
                side_effect=[products, products],
            ),
            patch(
                "ai.shopping_assistant.fetch_products",
            ) as mock_fetch_products,
            patch(
                "ai.shopping_assistant.fetch_offers_for_product_ids",
                return_value=offers,
            ),
            patch(
                "ai.shopping_assistant.fetch_stores_by_ids",
                return_value=[
                    {
                        "id": "store-1",
                        "name": "Store One",
                        "website": "https://store.test",
                    },
                ],
            ),
            patch(
                "ai.shopping_assistant.generate_shopping_response_with_llm",
                return_value=None,
            ),
            self.assertLogs("spario.retrieval", level="INFO") as captured,
        ):
            payload = shopping_assistant.answer_question_payload("tv")

        self.assertEqual(len(captured.records), 1)
        diagnostic = parse_log(captured.records[0])
        self.assertEqual(diagnostic["intent"], "category_recommendation")
        self.assertEqual(diagnostic["category"], "tv")
        self.assertIsNone(diagnostic["brand"])
        self.assertIsNone(diagnostic["budget"])
        self.assertTrue(diagnostic["bounded_retrieval_used"])
        self.assertEqual(diagnostic["bounded_candidates"], 20)
        self.assertFalse(diagnostic["legacy_fallback_used"])
        self.assertIsNone(diagnostic["fallback_reason"])
        self.assertEqual(diagnostic["products_passed_to_ranking"], 20)
        self.assertEqual(diagnostic["offer_product_ids"], 20)
        self.assertEqual(diagnostic["offers_loaded"], 20)
        self.assertEqual(diagnostic["final_products_returned"], 6)
        self.assertTrue(diagnostic["request_succeeded"])
        self.assertIsInstance(diagnostic["request_id"], str)
        self.assertEqual(len(diagnostic["request_id"]), 8)
        self.assertGreaterEqual(diagnostic["total_time_ms"], 0)
        mock_fetch_products.assert_not_called()

        self.assertEqual(set(payload), {"answer", "products"})
        self.assertEqual(
            set(payload["products"][0]),
            {
                "product_id",
                "name",
                "category",
                "image_url",
                "store_name",
                "price",
                "old_price",
                "discount_pct",
                "product_url",
                "availability",
                "data_confidence",
                "reason",
            },
        )

    def test_fallback_is_reported_in_summary(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="product_search",
            query="airpods max",
            normalized_question="airpods max",
            category="cuffie",
            keywords=("airpods", "max"),
            brand="apple",
            product_keywords=("airpods", "max"),
            model_terms=("max",),
        )
        airpods_max = product(
            "airpods-max",
            "Apple AirPods Max",
            "cuffie",
        )

        with (
            patch(
                "core.retrieval_diagnostics.get_retrieval_diagnostics_enabled",
                return_value=True,
            ),
            patch(
                "ai.shopping_assistant.parse_question",
                return_value=parsed,
            ),
            patch(
                "ai.shopping_assistant.fetch_candidate_products",
                return_value=[],
            ),
            patch(
                "ai.shopping_assistant.fetch_products",
                return_value=[airpods_max],
            ),
            patch(
                "ai.shopping_assistant.fetch_offers_for_product_ids",
                return_value=[offer("airpods-max", "store-1", 499)],
            ),
            patch(
                "ai.shopping_assistant.fetch_stores_by_ids",
                return_value=[{"id": "store-1", "name": "Store One"}],
            ),
            self.assertLogs("spario.retrieval", level="INFO") as captured,
        ):
            payload = shopping_assistant.answer_question_payload(
                "AirPods Max"
            )

        self.assertEqual(len(captured.records), 1)
        diagnostic = parse_log(captured.records[0])
        self.assertTrue(diagnostic["bounded_retrieval_used"])
        self.assertEqual(diagnostic["bounded_candidates"], 0)
        self.assertTrue(diagnostic["legacy_fallback_used"])
        self.assertEqual(
            diagnostic["fallback_reason"],
            "no_bounded_candidates",
        )
        self.assertEqual(diagnostic["products_passed_to_ranking"], 1)
        self.assertEqual(diagnostic["offer_product_ids"], 1)
        self.assertEqual(diagnostic["offers_loaded"], 1)
        self.assertEqual(diagnostic["final_products_returned"], 1)
        self.assertEqual(
            set(payload),
            {"answer", "products"},
        )


if __name__ == "__main__":
    unittest.main()
