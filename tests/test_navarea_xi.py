import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from navarea_xi_parser import parse_warning, convert_to_decimal, classify_hazard, parse_coordinates

class TestNavareaXIParser(unittest.TestCase):

    def test_sample_1_okinotori_shima(self):
        header = "NAVAREA XI NO.26-0451"
        raw = """NO.26-0451       Date:2026/10/09 07 UTC
NORTH PACIFIC, OKINOTORI SHIMA.
HATCH COVER, ABOUT 20 METRE IN SQUARE,
ADRIFT IN 
16-54.1N 134-39.5E AT 090625Z OCT.
CANCEL 0450/26.
CANCEL THIS MSG 120625Z OCT."""
        raw_msg, nav_warn, spatial = parse_warning(raw, header)
        self.assertEqual(nav_warn["warning_id"], "NAVAREA XI 0451/26")
        self.assertEqual(nav_warn["category"], "drifting")
        self.assertEqual(nav_warn["issued_text"], "2026/10/09 07 UTC")
        self.assertIsNotNone(spatial)
        self.assertEqual(spatial["type"], "Point")
        self.assertAlmostEqual(nav_warn["latitude"], 16.901667, places=4)
        self.assertAlmostEqual(nav_warn["longitude"], 134.658333, places=4)

from navarea_xi_sync import compute_differential

class TestDifferentialSync(unittest.TestCase):

    def setUp(self):
        self.scraped_warnings = [
            {"warning_id": "NAVAREA XI 0451/26", "title": "OKINOTORI SHIMA"},
            {"warning_id": "NAVAREA XI 0450/26", "title": "MARSHALLS"},
            {"warning_id": "NAVAREA XI 0999/26", "title": "Brand New Warning"}
        ]
        self.scraped_messages = [
            {"warning_id": "NAVAREA XI 0451/26", "checksum_sha256": "hash_451_unchanged"},
            {"warning_id": "NAVAREA XI 0450/26", "checksum_sha256": "hash_450_new_revision"},
            {"warning_id": "NAVAREA XI 0999/26", "checksum_sha256": "hash_999_brand_new"}
        ]
        self.existing_warnings = {
            "NAVAREA XI 0451/26": {"warning_id": "NAVAREA XI 0451/26", "status": "active"},
            "NAVAREA XI 0450/26": {"warning_id": "NAVAREA XI 0450/26", "status": "active"},
            "NAVAREA XI 0100/26": {"warning_id": "NAVAREA XI 0100/26", "status": "active"} 
        }
        self.existing_checksums = {
            ("NAVAREA XI 0451/26", "hash_451_unchanged"),
            ("NAVAREA XI 0450/26", "hash_450_old_version"),
            ("NAVAREA XI 0100/26", "hash_100_old")
        }

    def test_differential_bucketing(self):
        diff = compute_differential(
            self.scraped_warnings,
            self.scraped_messages,
            self.existing_warnings,
            self.existing_checksums
        )

        self.assertIn("NAVAREA XI 0451/26", diff["skip"])
        self.assertEqual(len(diff["skip"]), 1)

        new_ids = [w["warning_id"] for w, m in diff["new"]]
        self.assertIn("NAVAREA XI 0999/26", new_ids)
        self.assertEqual(len(diff["new"]), 1)

        update_ids = [w["warning_id"] for w, m in diff["update"]]
        self.assertIn("NAVAREA XI 0450/26", update_ids)
        self.assertEqual(len(diff["update"]), 1)

        self.assertIn("NAVAREA XI 0100/26", diff["cancel"])
        self.assertEqual(len(diff["cancel"]), 1)

if __name__ == "__main__":
    unittest.main()
