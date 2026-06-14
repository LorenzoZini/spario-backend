import os
import unittest
from unittest.mock import patch

from core import config
from core.supabase_client import (
    clear_supabase_client_cache,
    get_supabase_client,
)


class CoreConfigTests(unittest.TestCase):
    def test_missing_supabase_settings_raise_clear_error(self):
        with (
            patch.dict(
                os.environ,
                {"SUPABASE_URL": "", "SUPABASE_KEY": ""},
            ),
            patch.object(config, "SUPABASE_URL", None),
            patch.object(config, "SUPABASE_KEY", None),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "SUPABASE_URL, SUPABASE_KEY",
            ):
                config.require_supabase_settings()


class SupabaseClientTests(unittest.TestCase):
    def tearDown(self):
        clear_supabase_client_cache()

    @patch("core.supabase_client.create_client")
    @patch(
        "core.supabase_client.require_supabase_settings",
        return_value=("https://example.supabase.co", "test-key"),
    )
    def test_client_is_created_once_and_reused(
        self,
        mock_require_settings,
        mock_create_client,
    ):
        expected_client = object()
        mock_create_client.return_value = expected_client
        clear_supabase_client_cache()

        first = get_supabase_client()
        second = get_supabase_client()

        self.assertIs(first, expected_client)
        self.assertIs(second, expected_client)
        mock_require_settings.assert_called_once_with()
        mock_create_client.assert_called_once_with(
            "https://example.supabase.co",
            "test-key",
        )


if __name__ == "__main__":
    unittest.main()
