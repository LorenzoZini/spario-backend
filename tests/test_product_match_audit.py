import io
import unittest
from contextlib import redirect_stdout

from scripts import product_match_audit


def product(product_id, name, category="smartphone", search_keywords=None):
    return {
        "id": product_id,
        "name": name,
        "category": category,
        "search_keywords": search_keywords or name,
    }


class ProductMatchAuditTests(unittest.TestCase):
    def test_normalization_removes_noise_but_preserves_differentiators(self):
        tokens = product_match_audit.tokenize(
            "Offerta Apple iPhone 15 Pro Max, 256 GB, Blue Smartphone"
        )

        self.assertIn("apple", tokens)
        self.assertIn("iphone", tokens)
        self.assertIn("15", tokens)
        self.assertIn("pro", tokens)
        self.assertIn("max", tokens)
        self.assertIn("256gb", tokens)
        self.assertIn("blue", tokens)
        self.assertNotIn("offerta", tokens)
        self.assertNotIn("smartphone", tokens)

    def test_exact_duplicate_detection(self):
        report = product_match_audit.build_report({
            "products": [
                product("p1", "Apple AirPods Max", "cuffie"),
                product("p2", "Apple AirPods Max", "cuffie"),
            ],
            "product_offers": [],
        })

        self.assertEqual(
            report["summary"]["exact_normalized_duplicate_groups"],
            1,
        )
        self.assertEqual(
            report["summary"]["high_confidence_candidate_groups"],
            1,
        )

    def test_similar_title_detection(self):
        report = product_match_audit.build_report({
            "products": [
                product("p1", "Apple AirPods Max Argento", "cuffie"),
                product(
                    "p2",
                    "Apple AirPods Max cuffie wireless Bluetooth Argento",
                    "cuffie",
                ),
            ],
            "product_offers": [],
        })

        self.assertEqual(report["summary"]["candidate_groups_total"], 1)
        self.assertEqual(report["examples"][0]["confidence"], "HIGH")

    def test_pro_vs_non_pro_is_not_high_confidence(self):
        report = product_match_audit.build_report({
            "products": [
                product("p1", "Apple iPhone 15 128GB Nero"),
                product("p2", "Apple iPhone 15 Pro 128GB Nero"),
            ],
            "product_offers": [],
        })

        self.assertEqual(report["summary"]["candidate_groups_total"], 1)
        self.assertEqual(report["examples"][0]["confidence"], "LOW")
        self.assertIn("different_variant", report["examples"][0]["conflicts"])

    def test_different_storage_is_not_high_confidence(self):
        report = product_match_audit.build_report({
            "products": [
                product("p1", "Apple iPhone 15 Pro 128GB Nero"),
                product("p2", "Apple iPhone 15 Pro 256GB Nero"),
            ],
            "product_offers": [],
        })

        self.assertEqual(report["summary"]["candidate_groups_total"], 1)
        self.assertEqual(report["examples"][0]["confidence"], "LOW")
        self.assertIn(
            "different_capacity_storage",
            report["examples"][0]["conflicts"],
        )

    def test_different_screen_size_is_not_high_confidence(self):
        report = product_match_audit.build_report({
            "products": [
                product("p1", "Samsung QLED AI TV 55\" 4K Q4", "tv"),
                product("p2", "Samsung QLED AI TV 75\" 4K Q4", "tv"),
            ],
            "product_offers": [],
        })

        self.assertEqual(report["summary"]["candidate_groups_total"], 1)
        self.assertEqual(report["examples"][0]["confidence"], "LOW")
        self.assertIn("different_screen_size", report["examples"][0]["conflicts"])

    def test_same_category_is_safer_than_cross_category_matching(self):
        report = product_match_audit.build_report({
            "products": [
                product("p1", "Apple AirPods Max", "cuffie"),
                product("p2", "Apple AirPods Max", "accessori"),
            ],
            "product_offers": [],
        })

        self.assertEqual(report["summary"]["candidate_groups_total"], 0)

    def test_differentiator_conflict_downgrades_confidence(self):
        report = product_match_audit.build_report({
            "products": [
                product("p1", "Sony PS5 Slim Disc Edition", "gaming"),
                product("p2", "Sony PS5 Slim Digital Edition", "gaming"),
            ],
            "product_offers": [],
        })

        self.assertEqual(report["summary"]["candidate_groups_total"], 1)
        self.assertEqual(report["examples"][0]["confidence"], "LOW")
        self.assertIn("different_variant", report["examples"][0]["conflicts"])
        self.assertEqual(
            report["summary"]["groups_downgraded_due_to_differentiator_conflicts"],
            1,
        )

    def test_output_summary_shape_is_stable(self):
        report = product_match_audit.build_report({
            "products": [
                product("p1", "Apple AirPods Max", "cuffie"),
                product("p2", "Apple AirPods Max", "cuffie"),
            ],
            "product_offers": [
                {"id": "o1", "product_id": "p1", "store_id": "s1"},
                {"id": "o2", "product_id": "p2", "store_id": "s2"},
            ],
        })

        self.assertEqual(
            set(report["summary"]),
            {
                "total_products_analyzed",
                "categories_analyzed",
                "exact_normalized_duplicate_groups",
                "high_confidence_candidate_groups",
                "medium_confidence_candidate_groups",
                "low_confidence_similar_groups",
                "groups_downgraded_due_to_differentiator_conflicts",
                "candidate_groups_total",
                "warning",
            },
        )

        output = io.StringIO()
        with redirect_stdout(output):
            product_match_audit.print_report(report)

        text = output.getvalue()
        self.assertIn("# Spario Product Match Audit", text)
        self.assertIn("## Summary", text)
        self.assertIn("## Candidate Examples", text)
        self.assertIn("candidate only", text)


if __name__ == "__main__":
    unittest.main()
