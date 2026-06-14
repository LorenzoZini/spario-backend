import os
import unittest
from unittest.mock import patch


os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

from ai import shopping_assistant


class ShoppingAssistantOfferBatchTests(unittest.TestCase):
    @patch("ai.shopping_assistant.fetch_stores")
    @patch("ai.shopping_assistant.fetch_stores_by_ids")
    @patch("ai.shopping_assistant.fetch_offers_for_product")
    def test_get_best_offer_fetches_only_referenced_stores(
        self,
        mock_fetch_offers_for_product,
        mock_fetch_stores_by_ids,
        mock_fetch_stores,
    ):
        mock_fetch_offers_for_product.return_value = [
            {
                "id": "offer-1",
                "product_id": "product-1",
                "store_id": "store-1",
                "current_price": 100,
                "availability": "available",
                "condition": "new",
                "data_confidence": "alta",
            },
        ]
        mock_fetch_stores_by_ids.return_value = [
            {
                "id": "store-1",
                "name": "Store One",
                "website": "https://one.test",
            },
        ]

        best_offer = shopping_assistant.get_best_offer("product-1")

        mock_fetch_offers_for_product.assert_called_once_with("product-1")
        mock_fetch_stores_by_ids.assert_called_once()
        self.assertEqual(
            list(mock_fetch_stores_by_ids.call_args.args[0]),
            ["store-1"],
        )
        mock_fetch_stores.assert_not_called()
        self.assertEqual(best_offer["store_name"], "Store One")
        self.assertEqual(best_offer["price"], 100.0)

    @patch("ai.shopping_assistant.fetch_offers_for_product")
    @patch("ai.shopping_assistant.fetch_offers_for_product_ids")
    @patch("ai.shopping_assistant.fetch_stores")
    @patch("ai.shopping_assistant.fetch_stores_by_ids")
    def test_collect_offer_records_batches_and_preserves_product_order(
        self,
        mock_fetch_stores_by_ids,
        mock_fetch_stores,
        mock_fetch_offers_for_product_ids,
        mock_fetch_offers_for_product,
    ):
        products = [
            {
                "id": "product-1",
                "name": "Product One",
                "category": "tech",
                "image_url": None,
                "search_keywords": "product one",
            },
            {
                "id": "product-2",
                "name": "Product Two",
                "category": "tech",
                "image_url": None,
                "search_keywords": "product two",
            },
        ]
        mock_fetch_stores_by_ids.return_value = [
            {"id": "store-1", "name": "Store One", "website": "https://one.test"},
            {"id": "store-2", "name": "Store Two", "website": "https://two.test"},
        ]
        mock_fetch_offers_for_product_ids.return_value = [
            {
                "id": "offer-2",
                "product_id": "product-2",
                "store_id": "store-2",
                "current_price": 80,
                "old_price": None,
                "product_url": "https://two.test/product-2",
                "availability": "available",
                "condition": "new",
                "listing_type": "retail_online",
                "data_confidence": "alta",
            },
            {
                "id": "offer-1-high",
                "product_id": "product-1",
                "store_id": "store-2",
                "current_price": 120,
                "old_price": None,
                "product_url": "https://two.test/product-1",
                "availability": "available",
                "condition": "new",
                "listing_type": "retail_online",
                "data_confidence": "alta",
            },
            {
                "id": "offer-1-low",
                "product_id": "product-1",
                "store_id": "store-1",
                "current_price": 100,
                "old_price": 130,
                "product_url": "https://one.test/product-1",
                "availability": "available",
                "condition": "new",
                "listing_type": "retail_online",
                "data_confidence": "alta",
            },
        ]

        records = shopping_assistant.collect_offer_records(products)

        mock_fetch_offers_for_product_ids.assert_called_once_with(
            ["product-1", "product-2"]
        )
        mock_fetch_stores_by_ids.assert_called_once()
        self.assertEqual(
            list(mock_fetch_stores_by_ids.call_args.args[0]),
            ["store-2", "store-2", "store-1"],
        )
        mock_fetch_stores.assert_not_called()
        mock_fetch_offers_for_product.assert_not_called()
        self.assertEqual(
            [record["product"]["id"] for record in records],
            ["product-1", "product-2"],
        )
        self.assertEqual(records[0]["price"], 100.0)
        self.assertEqual(records[0]["offer"]["store_name"], "Store One")
        self.assertEqual(records[0]["offer"]["offers_checked"], 2)
        self.assertEqual(records[0]["discount_pct"], (30 / 130) * 100)
        self.assertEqual(records[1]["price"], 80.0)
        self.assertEqual(records[1]["offer"]["store_name"], "Store Two")
        self.assertEqual(
            set(shopping_assistant.product_card_from_record(records[0])),
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

    @patch("ai.shopping_assistant.fetch_offers_for_product")
    @patch("ai.shopping_assistant.fetch_offers_for_product_ids")
    @patch("ai.shopping_assistant.fetch_stores")
    @patch("ai.shopping_assistant.fetch_stores_by_ids")
    def test_empty_store_lookup_is_reused_without_refetching(
        self,
        mock_fetch_stores_by_ids,
        mock_fetch_stores,
        mock_fetch_offers_for_product_ids,
        mock_fetch_offers_for_product,
    ):
        products = [
            {"id": "product-1", "name": "Product One"},
            {"id": "product-2", "name": "Product Two"},
        ]
        mock_fetch_stores_by_ids.return_value = []
        mock_fetch_offers_for_product_ids.return_value = [
            {
                "id": "offer-1",
                "product_id": "product-1",
                "store_id": "missing-store",
                "current_price": 100,
                "availability": "available",
                "condition": "new",
                "data_confidence": "alta",
            },
            {
                "id": "offer-2",
                "product_id": "product-2",
                "store_id": "missing-store",
                "current_price": 80,
                "availability": "available",
                "condition": "new",
                "data_confidence": "alta",
            },
        ]

        records = shopping_assistant.collect_offer_records(products)

        mock_fetch_stores_by_ids.assert_called_once()
        self.assertEqual(
            list(mock_fetch_stores_by_ids.call_args.args[0]),
            ["missing-store", "missing-store"],
        )
        mock_fetch_stores.assert_not_called()
        mock_fetch_offers_for_product.assert_not_called()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["offer"]["store_name"], "Store sconosciuto")
        self.assertEqual(records[1]["offer"]["store_name"], "Store sconosciuto")


class ShoppingAssistantRequestReuseTests(unittest.TestCase):
    def test_answer_payload_reuses_precomputed_products_and_records(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="product_search",
            query="cuffie",
            normalized_question="cuffie",
            category="cuffie",
            budget=None,
            keywords=("cuffie",),
        )
        products = [{"id": "product-1", "name": "Product One"}]
        records = [{"product": products[0], "offer": {"store_name": "Store One"}}]
        cards = [{"product_id": "product-1", "name": "Product One"}]

        with (
            patch(
                "ai.shopping_assistant.parse_question",
                return_value=parsed,
            ),
            patch(
                "ai.shopping_assistant.products_and_records_for_parsed",
                return_value=(products, records),
            ) as mock_products_and_records,
            patch(
                "ai.shopping_assistant.product_cards_from_records",
                return_value=cards,
            ),
            patch(
                "ai.shopping_assistant.answer_question_from_parsed",
                return_value="Risposta fallback.",
            ) as mock_answer_from_parsed,
            patch(
                "ai.shopping_assistant.looks_product_specific_parsed",
                return_value=False,
            ),
            patch(
                "ai.shopping_assistant.generate_shopping_response_with_llm",
                return_value=None,
            ),
        ):
            payload = shopping_assistant.answer_question_payload("cuffie")

        mock_products_and_records.assert_called_once_with(parsed)
        mock_answer_from_parsed.assert_called_once_with(
            "cuffie",
            parsed,
            products=products,
            records=records,
        )
        self.assertEqual(
            payload,
            {
                "answer": "Risposta fallback.",
                "products": cards,
            },
        )


if __name__ == "__main__":
    unittest.main()
