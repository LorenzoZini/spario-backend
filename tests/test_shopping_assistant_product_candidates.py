import os
import unittest
from unittest.mock import patch


os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

from ai import shopping_assistant


def product(product_id, name, category, search_keywords=None):
    return {
        "id": product_id,
        "name": name,
        "category": category,
        "image_url": None,
        "search_keywords": search_keywords or name,
    }


class ShoppingAssistantProductCandidateTests(unittest.TestCase):
    def test_specific_budget_query_keeps_existing_product_retrieval(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="best_under_budget",
            query="samsung",
            normalized_question="samsung sotto 300",
            category="smartphone",
            budget=300,
            keywords=("samsung",),
            brand="samsung",
            product_keywords=("samsung",),
        )
        samsung = product(
            "samsung-1",
            "Samsung Galaxy",
            "smartphone",
        )

        with (
            patch(
                "ai.shopping_assistant.retrieve_products",
                return_value=[samsung],
            ) as mock_retrieve_products,
            patch(
                "ai.shopping_assistant.fetch_offer_first_product_ids",
            ) as mock_offer_first,
        ):
            actual = shopping_assistant.retrieve_products_with_offer_first(
                parsed,
                limit=160,
            )

        self.assertEqual(actual, [samsung])
        mock_retrieve_products.assert_called_once_with(parsed, limit=160)
        mock_offer_first.assert_not_called()

    def test_generic_discount_uses_offer_first_before_legacy(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="discount_ranking",
            query="sconto oggi",
            normalized_question="miglior sconto oggi",
            keywords=("sconto", "oggi"),
            sort_preference="discount",
        )
        products = [
            product("product-1", "Product One", "tech"),
            product("product-2", "Product Two", "tech"),
        ]

        with (
            patch(
                "ai.shopping_assistant.retrieve_products",
                return_value=[],
            ) as mock_retrieve_products,
            patch(
                "ai.shopping_assistant.fetch_offer_first_product_ids",
                return_value=["product-1", "product-2"],
            ) as mock_offer_first,
            patch(
                "ai.shopping_assistant.fetch_products_by_ids",
                return_value=products,
            ),
            patch(
                "ai.shopping_assistant.rank_product_candidates",
                return_value=[],
            ) as mock_rank_candidates,
            patch(
                "ai.shopping_assistant.fetch_products",
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products_with_offer_first(
                parsed,
                limit=160,
            )

        self.assertEqual(actual, products)
        mock_retrieve_products.assert_called_once_with(
            parsed,
            limit=160,
            allow_legacy_fallback=False,
        )
        mock_offer_first.assert_called_once_with(
            reason="discount",
            budget=None,
        )
        mock_rank_candidates.assert_called_once_with(
            products,
            parsed,
            160,
        )
        mock_fetch_products.assert_not_called()

    def test_generic_budget_uses_offer_first_before_legacy(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="best_under_budget",
            query="",
            normalized_question="prodotto tech sotto 100",
            budget=100,
            sort_preference="lowest_price",
        )
        products = [
            product("product-1", "Product One", "tech"),
            product("product-2", "Product Two", "tech"),
        ]
        ranked_products = [products[1], products[0]]

        with (
            patch(
                "ai.shopping_assistant.retrieve_products",
                return_value=[],
            ),
            patch(
                "ai.shopping_assistant.fetch_offer_first_product_ids",
                return_value=["product-1", "product-2"],
            ) as mock_offer_first,
            patch(
                "ai.shopping_assistant.fetch_products_by_ids",
                return_value=products,
            ),
            patch(
                "ai.shopping_assistant.rank_product_candidates",
                return_value=ranked_products,
            ) as mock_rank_candidates,
            patch(
                "ai.shopping_assistant.fetch_products",
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products_with_offer_first(
                parsed,
                limit=300,
            )

        self.assertEqual(actual, ranked_products)
        mock_offer_first.assert_called_once_with(
            reason="budget",
            budget=100,
        )
        mock_rank_candidates.assert_called_once_with(
            products,
            parsed,
            300,
        )
        mock_fetch_products.assert_not_called()

    def test_empty_offer_first_candidates_keep_legacy_fallback(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="discount_ranking",
            query="sconto oggi",
            normalized_question="miglior sconto oggi",
            keywords=("sconto", "oggi"),
            sort_preference="discount",
        )
        legacy_products = [
            product("product-1", "Legacy Product", "tech"),
        ]

        with (
            patch(
                "ai.shopping_assistant.retrieve_products",
                return_value=[],
            ),
            patch(
                "ai.shopping_assistant.fetch_offer_first_product_ids",
                return_value=[],
            ),
            patch(
                "ai.shopping_assistant.fetch_products",
                return_value=legacy_products,
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products_with_offer_first(
                parsed,
                limit=160,
            )

        self.assertEqual(actual, legacy_products)
        mock_fetch_products.assert_called_once_with()

    def test_missing_offer_first_products_keep_legacy_fallback(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="discount_ranking",
            query="sconto oggi",
            normalized_question="miglior sconto oggi",
            keywords=("sconto", "oggi"),
            sort_preference="discount",
        )
        legacy_products = [
            product("product-1", "Legacy Product", "tech"),
        ]

        with (
            patch(
                "ai.shopping_assistant.retrieve_products",
                return_value=[],
            ),
            patch(
                "ai.shopping_assistant.fetch_offer_first_product_ids",
                return_value=["missing-product"],
            ),
            patch(
                "ai.shopping_assistant.fetch_products_by_ids",
                return_value=[],
            ),
            patch(
                "ai.shopping_assistant.fetch_products",
                return_value=legacy_products,
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products_with_offer_first(
                parsed,
                limit=160,
            )

        self.assertEqual(actual, legacy_products)
        mock_fetch_products.assert_called_once_with()

    def test_discount_records_still_use_existing_final_ranking(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="discount_ranking",
            query="sconto oggi",
            normalized_question="miglior sconto oggi",
            keywords=("sconto", "oggi"),
            sort_preference="discount",
        )
        products = [product("product-1", "Product One", "tech")]
        records = [
            {
                "product": products[0],
                "offer": {"store_name": "Store One"},
                "price": 80,
                "old_price": 100,
                "discount_pct": 20,
            },
        ]
        ranked_records = [dict(records[0], ranking_score=123)]

        with (
            patch(
                "ai.shopping_assistant.retrieve_products_with_offer_first",
                return_value=products,
            ),
            patch(
                "ai.shopping_assistant.collect_offer_records",
                return_value=records,
            ),
            patch(
                "ai.shopping_assistant.rank_offer_records",
                return_value=ranked_records,
            ) as mock_rank_offer_records,
        ):
            actual_products, actual_records = (
                shopping_assistant.products_and_records_for_parsed(parsed)
            )

        self.assertEqual(actual_products, products)
        self.assertEqual(actual_records, ranked_records)
        mock_rank_offer_records.assert_called_once_with(records, parsed)

    def test_category_candidates_preserve_legacy_ranking(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="category_recommendation",
            query="tv",
            normalized_question="tv",
            category="tv",
            keywords=("tv",),
        )
        all_products = [
            product("tv-1", "LG OLED TV", "tv"),
            product("tv-2", "Samsung Smart TV", "tv"),
            product("tv-3", "Sony TV", "tv"),
            product("other-1", "Apple iPhone 16", "smartphone"),
        ]
        expected = shopping_assistant.rank_product_candidates(
            all_products,
            parsed,
            limit=3,
        )

        def fetch_candidates(**kwargs):
            if kwargs.get("category_values"):
                return all_products[:3]
            return [all_products[0], all_products[1]]

        with (
            patch(
                "ai.shopping_assistant.fetch_candidate_products",
                side_effect=fetch_candidates,
            ) as mock_fetch_candidates,
            patch(
                "ai.shopping_assistant.fetch_products",
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products(parsed, limit=3)

        self.assertEqual(actual, expected)
        self.assertEqual(mock_fetch_candidates.call_count, 2)
        mock_fetch_products.assert_not_called()

    def test_brand_query_prioritizes_exact_product_without_full_scan(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="product_search",
            query="iphone 16",
            normalized_question="iphone 16",
            category="smartphone",
            keywords=("iphone",),
            brand="apple",
            product_keywords=("iphone",),
            model_terms=("16",),
        )
        iphone = product(
            "iphone-16",
            "Apple iPhone 16",
            "smartphone",
            "apple iphone 16",
        )
        generic = product(
            "generic-phone",
            "Generic Smartphone",
            "smartphone",
        )

        with (
            patch(
                "ai.shopping_assistant.fetch_candidate_products",
                side_effect=[[generic], [iphone]],
            ),
            patch(
                "ai.shopping_assistant.fetch_products",
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products(parsed, limit=5)

        self.assertEqual(actual, [iphone])
        mock_fetch_products.assert_not_called()

    def test_generic_need_query_uses_bounded_term_candidates(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="product_search",
            query="wireless",
            normalized_question="wireless",
            keywords=("wireless",),
            needs=("wireless",),
        )
        wireless_products = [
            product(
                f"headphones-{index}",
                f"Wireless Headphones {index}",
                "cuffie",
            )
            for index in range(1, 4)
        ]
        expected = shopping_assistant.rank_product_candidates(
            wireless_products,
            parsed,
            limit=3,
        )

        with (
            patch(
                "ai.shopping_assistant.fetch_candidate_products",
                return_value=wireless_products,
            ) as mock_fetch_candidates,
            patch(
                "ai.shopping_assistant.fetch_products",
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products(parsed, limit=3)

        self.assertEqual(actual, expected)
        mock_fetch_candidates.assert_called_once()
        mock_fetch_products.assert_not_called()

    def test_category_budget_query_keeps_product_ranking_unchanged(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="best_under_budget",
            query="tv",
            normalized_question="tv sotto 500 euro",
            category="tv",
            budget=500,
            keywords=("tv",),
        )
        candidates = [
            product("tv-1", "LG OLED TV", "tv"),
            product("tv-2", "Samsung Smart TV", "tv"),
            product("tv-3", "Sony TV", "tv"),
        ]
        expected = shopping_assistant.rank_product_candidates(
            candidates,
            parsed,
            limit=3,
        )

        with (
            patch(
                "ai.shopping_assistant.fetch_candidate_products",
                side_effect=[candidates, candidates],
            ),
            patch(
                "ai.shopping_assistant.fetch_products",
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products(parsed, limit=3)

        self.assertEqual(actual, expected)
        mock_fetch_products.assert_not_called()

    def test_empty_query_keeps_legacy_fallback(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="product_search",
            query="",
            normalized_question="",
        )
        all_products = [
            product("product-1", "Generic Product", "tech"),
        ]

        with (
            patch(
                "ai.shopping_assistant.fetch_candidate_products",
            ) as mock_fetch_candidates,
            patch(
                "ai.shopping_assistant.fetch_products",
                return_value=all_products,
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products(parsed, limit=5)

        self.assertEqual(
            actual,
            shopping_assistant.rank_product_candidates(
                all_products,
                parsed,
                limit=5,
            ),
        )
        mock_fetch_candidates.assert_not_called()
        mock_fetch_products.assert_called_once_with()

    def test_no_bounded_candidates_falls_back_to_legacy_products(self):
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
            "apple airpods max",
        )

        with (
            patch(
                "ai.shopping_assistant.fetch_candidate_products",
                return_value=[],
            ),
            patch(
                "ai.shopping_assistant.fetch_products",
                return_value=[airpods_max],
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products(parsed, limit=5)

        self.assertEqual(actual, [airpods_max])
        mock_fetch_products.assert_called_once_with()

    def test_too_few_category_candidates_use_legacy_fallback(self):
        parsed = shopping_assistant.ParsedQuestion(
            intent="category_recommendation",
            query="tv",
            normalized_question="tv",
            category="tv",
            keywords=("tv",),
        )
        bounded_product = product("tv-1", "LG OLED TV", "tv")
        legacy_products = [
            bounded_product,
            product("tv-2", "Samsung Smart TV", "tv"),
            product("tv-3", "Sony TV", "tv"),
        ]
        expected = shopping_assistant.rank_product_candidates(
            legacy_products,
            parsed,
            limit=3,
        )

        with (
            patch(
                "ai.shopping_assistant.fetch_candidate_products",
                return_value=[bounded_product],
            ),
            patch(
                "ai.shopping_assistant.fetch_products",
                return_value=legacy_products,
            ) as mock_fetch_products,
        ):
            actual = shopping_assistant.retrieve_products(parsed, limit=3)

        self.assertEqual(actual, expected)
        mock_fetch_products.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
