import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from repositories import catalog_repository


class CatalogRepositoryTests(unittest.TestCase):
    def test_build_store_lookup_indexes_existing_store_rows(self):
        stores = [
            {
                "id": "store-1",
                "name": "Store One",
                "website": "https://one.test",
            },
            {
                "id": "store-2",
                "name": "Store Two",
                "website": "https://two.test",
            },
        ]

        lookup = catalog_repository.build_store_lookup(stores)

        self.assertEqual(
            lookup,
            {
                "store-1": stores[0],
                "store-2": stores[1],
            },
        )

    @patch("repositories.catalog_repository.get_supabase_client")
    def test_fetch_stores_by_ids_filters_and_deduplicates_ids(
        self,
        mock_get_client,
    ):
        client = MagicMock()
        query = client.table.return_value.select.return_value
        query.in_.return_value.execute.return_value = SimpleNamespace(
            data=[
                {"id": "store-1", "name": "Store One"},
                {"id": "store-2", "name": "Store Two"},
            ]
        )
        mock_get_client.return_value = client

        stores = catalog_repository.fetch_stores_by_ids(
            ["store-1", "store-2", "store-1", None, "", 123]
        )

        self.assertEqual(
            stores,
            [
                {"id": "store-1", "name": "Store One"},
                {"id": "store-2", "name": "Store Two"},
            ],
        )
        client.table.assert_called_once_with("stores")
        client.table.return_value.select.assert_called_once_with(
            catalog_repository.STORE_COLUMNS
        )
        query.in_.assert_called_once_with(
            "id",
            ["store-1", "store-2"],
        )

    @patch("repositories.catalog_repository.get_supabase_client")
    def test_fetch_stores_by_ids_skips_empty_input(self, mock_get_client):
        stores = catalog_repository.fetch_stores_by_ids(
            [None, "", "   ", 123]
        )

        self.assertEqual(stores, [])
        mock_get_client.assert_not_called()

    @patch.object(catalog_repository, "STORE_ID_CHUNK_SIZE", 2)
    @patch("repositories.catalog_repository.get_supabase_client")
    def test_fetch_stores_by_ids_chunks_large_id_lists(
        self,
        mock_get_client,
    ):
        client = MagicMock()
        query = client.table.return_value.select.return_value
        query.in_.return_value = query
        query.execute.side_effect = [
            SimpleNamespace(
                data=[
                    {"id": "store-1", "name": "Store One"},
                    {"id": "store-2", "name": "Store Two"},
                ]
            ),
            SimpleNamespace(
                data=[{"id": "store-3", "name": "Store Three"}]
            ),
        ]
        mock_get_client.return_value = client

        stores = catalog_repository.fetch_stores_by_ids(
            ["store-1", "store-2", "store-1", "store-3"]
        )

        self.assertEqual(
            query.in_.call_args_list,
            [
                call("id", ["store-1", "store-2"]),
                call("id", ["store-3"]),
            ],
        )
        self.assertEqual(
            stores,
            [
                {"id": "store-1", "name": "Store One"},
                {"id": "store-2", "name": "Store Two"},
                {"id": "store-3", "name": "Store Three"},
            ],
        )

    @patch("repositories.catalog_repository.get_supabase_client")
    def test_fetch_products_preserves_columns_and_pagination(self, mock_get_client):
        client = MagicMock()
        query = client.table.return_value.select.return_value
        query.range.return_value.execute.side_effect = [
            SimpleNamespace(data=[{"id": str(index)} for index in range(1000)]),
            SimpleNamespace(data=[{"id": "last"}]),
        ]
        mock_get_client.return_value = client

        products = catalog_repository.fetch_products()

        self.assertEqual(len(products), 1001)
        self.assertEqual(products[-1], {"id": "last"})
        self.assertEqual(
            client.table.call_args_list,
            [call("products"), call("products")],
        )
        client.table.return_value.select.assert_called_with(
            catalog_repository.PRODUCT_COLUMNS
        )
        self.assertEqual(
            query.range.call_args_list,
            [call(0, 999), call(1000, 1999)],
        )

    @patch("repositories.catalog_repository.get_supabase_client")
    def test_fetch_offers_filters_by_product_id(self, mock_get_client):
        client = MagicMock()
        query = client.table.return_value.select.return_value
        query.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "offer-1", "product_id": "product-1"}]
        )
        mock_get_client.return_value = client

        offers = catalog_repository.fetch_offers_for_product("product-1")

        self.assertEqual(
            offers,
            [{"id": "offer-1", "product_id": "product-1"}],
        )
        client.table.assert_called_once_with("product_offers")
        client.table.return_value.select.assert_called_once_with(
            catalog_repository.OFFER_COLUMNS
        )
        query.eq.assert_called_once_with("product_id", "product-1")

    @patch("repositories.catalog_repository.get_supabase_client")
    def test_fetch_offers_for_product_ids_uses_single_batched_filter(
        self,
        mock_get_client,
    ):
        client = MagicMock()
        query = client.table.return_value.select.return_value
        query.in_.return_value = query
        query.order.return_value = query
        query.range.return_value = query
        query.execute.return_value = SimpleNamespace(
            data=[
                {"id": "offer-1", "product_id": "product-1"},
                {"id": "offer-2", "product_id": "product-2"},
            ]
        )
        mock_get_client.return_value = client

        offers = catalog_repository.fetch_offers_for_product_ids(
            ["product-1", "product-2", "product-1", None]
        )

        self.assertEqual(
            offers,
            [
                {"id": "offer-1", "product_id": "product-1"},
                {"id": "offer-2", "product_id": "product-2"},
            ],
        )
        client.table.assert_called_once_with("product_offers")
        client.table.return_value.select.assert_called_once_with(
            catalog_repository.OFFER_COLUMNS
        )
        query.in_.assert_called_once_with(
            "product_id",
            ["product-1", "product-2"],
        )
        self.assertEqual(
            query.order.call_args_list,
            [
                call("product_id"),
                call("current_price", nullsfirst=False),
                call("id"),
            ],
        )
        query.range.assert_called_once_with(
            0,
            catalog_repository.OFFER_PAGE_SIZE - 1,
        )

    @patch("repositories.catalog_repository.get_supabase_client")
    def test_fetch_offers_for_product_ids_skips_empty_input(
        self,
        mock_get_client,
    ):
        offers = catalog_repository.fetch_offers_for_product_ids(
            [None, "", "   ", 123]
        )

        self.assertEqual(offers, [])
        mock_get_client.assert_not_called()

    @patch.object(catalog_repository, "OFFER_PRODUCT_ID_CHUNK_SIZE", 2)
    @patch("repositories.catalog_repository.get_supabase_client")
    def test_fetch_offers_for_product_ids_splits_ids_into_stable_chunks(
        self,
        mock_get_client,
    ):
        client = MagicMock()
        query = client.table.return_value.select.return_value
        query.in_.return_value = query
        query.order.return_value = query
        query.range.return_value = query
        query.execute.side_effect = [
            SimpleNamespace(
                data=[{"id": "offer-1", "product_id": "product-1"}]
            ),
            SimpleNamespace(
                data=[{"id": "offer-3", "product_id": "product-3"}]
            ),
        ]
        mock_get_client.return_value = client

        offers = catalog_repository.fetch_offers_for_product_ids(
            ["product-1", "product-2", "product-1", "product-3"]
        )

        self.assertEqual(
            query.in_.call_args_list,
            [
                call("product_id", ["product-1", "product-2"]),
                call("product_id", ["product-3"]),
            ],
        )
        self.assertEqual(
            query.order.call_args_list,
            [
                call("product_id"),
                call("current_price", nullsfirst=False),
                call("id"),
                call("product_id"),
                call("current_price", nullsfirst=False),
                call("id"),
            ],
        )
        self.assertEqual(
            offers,
            [
                {"id": "offer-1", "product_id": "product-1"},
                {"id": "offer-3", "product_id": "product-3"},
            ],
        )

    @patch.object(catalog_repository, "OFFER_PAGE_SIZE", 2)
    @patch("repositories.catalog_repository.get_supabase_client")
    def test_fetch_offers_for_product_ids_combines_paginated_pages(
        self,
        mock_get_client,
    ):
        client = MagicMock()
        query = client.table.return_value.select.return_value
        query.in_.return_value = query
        query.order.return_value = query
        query.range.return_value = query
        query.execute.side_effect = [
            SimpleNamespace(
                data=[
                    {"id": "offer-1", "product_id": "product-1"},
                    {"id": "offer-2", "product_id": "product-1"},
                ]
            ),
            SimpleNamespace(
                data=[{"id": "offer-3", "product_id": "product-1"}]
            ),
        ]
        mock_get_client.return_value = client

        offers = catalog_repository.fetch_offers_for_product_ids(
            ["product-1"]
        )

        self.assertEqual(
            query.range.call_args_list,
            [call(0, 1), call(2, 3)],
        )
        self.assertEqual(
            query.order.call_args_list,
            [
                call("product_id"),
                call("current_price", nullsfirst=False),
                call("id"),
                call("product_id"),
                call("current_price", nullsfirst=False),
                call("id"),
            ],
        )
        self.assertEqual(
            offers,
            [
                {"id": "offer-1", "product_id": "product-1"},
                {"id": "offer-2", "product_id": "product-1"},
                {"id": "offer-3", "product_id": "product-1"},
            ],
        )

    @patch("repositories.catalog_repository.get_supabase_client")
    def test_fetch_history_filters_by_product_id(self, mock_get_client):
        client = MagicMock()
        query = client.table.return_value.select.return_value
        query.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "history-1", "product_id": "product-1"}]
        )
        mock_get_client.return_value = client

        history = catalog_repository.fetch_history_for_product("product-1")

        self.assertEqual(
            history,
            [{"id": "history-1", "product_id": "product-1"}],
        )
        client.table.assert_called_once_with("price_history")
        client.table.return_value.select.assert_called_once_with(
            catalog_repository.HISTORY_COLUMNS
        )
        query.eq.assert_called_once_with("product_id", "product-1")


if __name__ == "__main__":
    unittest.main()
