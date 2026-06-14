import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

from api.ask_spario import ERROR_ANSWER, app


class AskSparioApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "status": "ok",
                "service": "spario-ai-backend",
            },
        )

    @patch("api.ask_spario.answer_question_payload")
    def test_ask_spario_preserves_success_response_shape(self, mock_answer):
        mock_answer.return_value = {
            "answer": "Ho trovato questo prodotto tra quelli tracciati.",
            "products": [
                {
                    "product_id": "product-1",
                    "name": "Prodotto reale",
                    "store_name": "Store reale",
                    "price": 99.99,
                }
            ],
        }

        response = self.client.post(
            "/api/ask-spario",
            json={"question": "dove costa meno?"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "answer": "Ho trovato questo prodotto tra quelli tracciati.",
                "products": [
                    {
                        "product_id": "product-1",
                        "name": "Prodotto reale",
                        "store_name": "Store reale",
                        "price": 99.99,
                    }
                ],
            },
        )
        mock_answer.assert_called_once_with("dove costa meno?")

    def test_empty_question_preserves_error_response_shape(self):
        response = self.client.post(
            "/api/ask-spario",
            json={"question": "   "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": False,
                "answer": ERROR_ANSWER,
            },
        )

    @patch("api.ask_spario.answer_question_payload")
    def test_assistant_error_uses_safe_fallback(self, mock_answer):
        mock_answer.side_effect = RuntimeError("simulated backend failure")

        response = self.client.post(
            "/api/ask-spario",
            json={"question": "cuffie sotto 100 euro"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": False,
                "answer": ERROR_ANSWER,
            },
        )


if __name__ == "__main__":
    unittest.main()
