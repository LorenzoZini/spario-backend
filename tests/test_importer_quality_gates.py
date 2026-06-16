import json
import tempfile
import unittest
from pathlib import Path

from importers import quality_gates


def valid_candidate(**overrides):
    candidate = {
        "name": "Apple AirPods Pro 2 USB-C Auricolari Wireless",
        "store_name": "Unieuro",
        "current_price": "199.99",
        "old_price": "249.99",
        "product_url": "https://example.test/product",
        "category": "cuffie",
        "image_url": "https://example.test/image.jpg",
        "availability": "available",
        "source": "unieuro",
    }
    candidate.update(overrides)
    return candidate


class ImporterQualityGatesTests(unittest.TestCase):
    def test_valid_candidate_is_accepted(self):
        result = quality_gates.evaluate_candidate(valid_candidate())

        self.assertTrue(result.accepted)
        self.assertEqual(result.severity, "WARNING")
        self.assertIn(result.confidence, {"medium", "high"})
        self.assertEqual(result.discard_reasons, [])
        self.assertEqual(result.normalized_category, "cuffie")
        self.assertIn(
            "important_differentiators_detected",
            result.warnings,
        )

    def test_missing_name_is_rejected(self):
        result = quality_gates.evaluate_candidate(valid_candidate(name=""))

        self.assertFalse(result.accepted)
        self.assertEqual(result.severity, "CRITICAL")
        self.assertIn("missing_name", result.discard_reasons)

    def test_missing_url_is_rejected(self):
        result = quality_gates.evaluate_candidate(valid_candidate(product_url=""))

        self.assertFalse(result.accepted)
        self.assertIn("missing_url", result.discard_reasons)

    def test_invalid_price_is_rejected(self):
        result = quality_gates.evaluate_candidate(valid_candidate(current_price="-1"))

        self.assertFalse(result.accepted)
        self.assertIn("invalid_price", result.discard_reasons)

    def test_old_price_lower_than_current_price_warns(self):
        result = quality_gates.evaluate_candidate(
            valid_candidate(current_price=200, old_price=100)
        )

        self.assertTrue(result.accepted)
        self.assertIn("old_price_lower_than_current_price", result.warnings)

    def test_missing_image_warns_not_rejects(self):
        result = quality_gates.evaluate_candidate(valid_candidate(image_url=""))

        self.assertTrue(result.accepted)
        self.assertIn("missing_image", result.warnings)

    def test_long_title_warns(self):
        result = quality_gates.evaluate_candidate(
            valid_candidate(name="Samsung " + ("Galaxy " * 30))
        )

        self.assertTrue(result.accepted)
        self.assertIn("title_too_long", result.warnings)

    def test_unknown_category_warns_not_silent(self):
        result = quality_gates.evaluate_candidate(
            valid_candidate(category="giardinaggio")
        )

        self.assertTrue(result.accepted)
        self.assertIsNone(result.normalized_category)
        self.assertIn("unknown_category", result.warnings)

    def test_laptop_category_is_allowed_but_cautious(self):
        result = quality_gates.evaluate_candidate(
            valid_candidate(
                name="HP 15-fd0099nl Intel Core 5 16GB RAM 512GB SSD",
                category="laptop",
            )
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.normalized_category, "laptop")
        self.assertEqual(result.matching_risk, "high")
        self.assertIn("category_high_matching_complexity", result.warnings)

    def test_important_differentiators_are_detected_and_preserved(self):
        result = quality_gates.evaluate_candidate(
            valid_candidate(
                name="Sony PS5 Slim Digital Edition Bundle 1TB White",
                category="gaming",
            )
        )

        differentiators = result.title_quality["important_differentiators"]
        self.assertIn("digital_edition", differentiators)
        self.assertIn("slim", differentiators)
        self.assertIn("bundle", differentiators)
        self.assertIn("1tb", differentiators)
        self.assertIn("important_differentiators_detected", result.warnings)
        self.assertIn("possible_bundle_or_condition_variant", result.warnings)

    def test_dry_run_report_counts_are_correct(self):
        candidates = [
            valid_candidate(),
            valid_candidate(product_url=""),
            valid_candidate(image_url=""),
            valid_candidate(category="giardinaggio"),
        ]

        report = quality_gates.dry_run_quality_report(candidates, example_limit=2)
        summary = report["summary"]

        self.assertEqual(summary["total_candidates"], 4)
        self.assertEqual(summary["accepted_candidates"], 3)
        self.assertEqual(summary["rejected_candidates"], 1)
        self.assertEqual(summary["candidates_with_warnings"], 3)
        self.assertEqual(summary["counts_by_discard_reason"]["missing_url"], 1)
        self.assertEqual(summary["counts_by_warning"]["missing_image"], 1)
        self.assertEqual(summary["counts_by_warning"]["unknown_category"], 1)
        self.assertEqual(summary["counts_by_normalized_category"]["cuffie"], 3)

    def test_summary_output_shape_is_stable(self):
        report = quality_gates.dry_run_quality_report([valid_candidate()])

        self.assertEqual(
            set(report),
            {"summary", "results"},
        )
        self.assertEqual(
            set(report["summary"]),
            {
                "total_candidates",
                "accepted_candidates",
                "rejected_candidates",
                "candidates_with_warnings",
                "counts_by_discard_reason",
                "counts_by_warning",
                "counts_by_normalized_category",
                "confidence_counts",
                "average_confidence",
                "examples",
                "summary",
            },
        )
        self.assertEqual(
            set(report["results"][0]),
            {
                "accepted",
                "severity",
                "confidence",
                "discard_reasons",
                "warnings",
                "normalized_category",
                "title_quality",
                "matching_risk",
                "summary",
            },
        )

    def test_local_json_loader_accepts_list_or_candidates_object(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "candidates.json"
            path.write_text(
                json.dumps({"candidates": [valid_candidate()]}),
                encoding="utf-8",
            )

            loaded = quality_gates.load_candidates_from_json(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["store_name"], "Unieuro")


if __name__ == "__main__":
    unittest.main()
