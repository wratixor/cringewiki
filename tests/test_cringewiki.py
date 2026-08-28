"""Core tests for the minimal server."""

import tempfile
import unittest
from pathlib import Path

from server.db import connect, initialize
from server.index import build_index
from server.influence import calculate_influence
from server.security import hash_password, verify_password
from server.seed import seed


class InfluenceTests(unittest.TestCase):
    def test_mutual_subscription_conserves_mass(self):
        weights = calculate_influence([10, 20], {1: [20], 2: [10]}, {10: 1, 20: 2})
        self.assertAlmostEqual(sum(weights.values()), 2.0, places=10)
        self.assertAlmostEqual(weights[10], 1.0, places=10)
        self.assertAlmostEqual(weights[20], 1.0, places=10)

    def test_article_absorbs_forwarded_mass(self):
        weights = calculate_influence([10], {1: [30]}, {10: 1})
        self.assertAlmostEqual(weights[10], 0.25)
        self.assertAlmostEqual(weights[30], 0.75)
        self.assertAlmostEqual(sum(weights.values()), 1.0)


class PersistenceTests(unittest.TestCase):
    def test_password_round_trip(self):
        salt, digest = hash_password("correct horse battery staple")
        self.assertTrue(verify_password("correct horse battery staple", salt, digest))
        self.assertFalse(verify_password("wrong password", salt, digest))

    def test_seed_builds_navigable_conserving_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.sqlite3"
            initialize(path)
            self.assertTrue(seed(path)); self.assertFalse(seed(path))
            with connect(path) as connection:
                payload = build_index(connection)
            self.assertEqual(len(payload["concepts"]), 10)
            self.assertEqual(payload["mass"]["users"], 5)
            self.assertAlmostEqual(payload["mass"]["total"], 5.0, places=9)
            concepts = {item["id"]: item for item in payload["concepts"]}
            self.assertIn("detektor-bazy", concepts["benefis-krinzha"]["linkedIds"])
            self.assertEqual(len(concepts["benefis-krinzha"]["coordinates"]), 6)


if __name__ == "__main__":
    unittest.main()
