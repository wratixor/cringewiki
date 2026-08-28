"""Core tests for the minimal server."""

import tempfile
import unittest
import sqlite3
from pathlib import Path

from server.app import ApiError, Handler
from server.db import SCHEMA, connect, initialize
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
            self.assertTrue(all(1 <= value <= 10 for item in payload["concepts"] for value in item["coordinates"]))

    def test_old_base_coordinates_are_migrated_to_ten_point_scale(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "old.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(SCHEMA.replace("BETWEEN 1 AND 10", "BETWEEN 1 AND 99"))
            connection.execute(
                "INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES (?,?,?,?,?,?,?,?,?)",
                ("old-point", "article", "Old", 1, 12, 25, 50, 75, 99),
            )
            connection.commit(); connection.close()
            initialize(path)
            with connect(path) as migrated:
                coordinates = migrated.execute("SELECT c0,c1,c2,c3,c4,c5 FROM points").fetchone()
                self.assertEqual(list(coordinates), [1, 2, 3, 6, 8, 10])
                with self.assertRaises(sqlite3.IntegrityError):
                    migrated.execute(
                        "INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES (?,?,?,?,?,?,?,?,?)",
                        ("invalid", "article", "Invalid", 11, 1, 1, 1, 1, 1),
                    )

    def test_api_rejects_starting_coordinate_above_ten(self):
        with self.assertRaises(ApiError):
            Handler._coordinates({"coordinates": [1, 2, 3, 4, 5, 11]})


if __name__ == "__main__":
    unittest.main()
