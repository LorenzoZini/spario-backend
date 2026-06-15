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
