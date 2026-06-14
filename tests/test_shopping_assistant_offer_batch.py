import os
import unittest
from unittest.mock import patch


os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

from ai import shopping_assistant


class ShoppingAssistantOfferBatchTests(unittest.TestCase):
    @patch("ai.shopping_assistant.fetch_offers_for_product")
    @patch("ai.shopping_assistant.fetch_offers_for_product_ids")
    @patch("ai.shopping_assistant.fetch_stores")
    def test_collect_offer_records_batches_and_preserves_product_order(
        self,
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
        mock_fetch_stores.return_value = [
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


if __name__ == "__main__":
    unittest.main()
