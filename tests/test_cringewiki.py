"""Core tests for the minimal server."""

import tempfile
import unittest
import sqlite3
from pathlib import Path

from server.app import ApiError, Handler
from server.db import SCHEMA, connect, initialize
from server.index import build_index
from server.influence import calculate_influence
from server.git_wiki import GitWikiError, sync_repository_wiki
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
            self.assertEqual(len(payload["concepts"]), 14)
            self.assertEqual(payload["mass"]["users"], 5)
            self.assertAlmostEqual(payload["mass"]["total"], 5.0, places=9)
            concepts = {item["id"]: item for item in payload["concepts"]}
            self.assertTrue(all(item["title"] for item in concepts.values()))
            self.assertIn("detektor-bazy", concepts["benefis-krinzha"]["linkedIds"])
            self.assertEqual(concepts["rickroll"]["actionUrl"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertEqual(concepts["users"]["kind"], "system")
            self.assertEqual(concepts["tags"]["kind"], "system")
            self.assertEqual(concepts["home"]["kind"], "system")
            self.assertEqual(payload["homeId"], "home")
            self.assertEqual(concepts["rickroll"]["actionUrl"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertIn("rickroll", concepts["home"]["linkedIds"])
            user_coordinates = [concept["coordinates"] for concept in concepts.values() if concept["kind"] == "user"]
            self.assertEqual(
                concepts["users"]["coordinates"],
                [1 + sum(values[index] for values in user_coordinates) / 100 for index in range(6)],
            )
            self.assertEqual(len(concepts["users"]["linkedIds"]), 6)
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

    def test_empty_article_keeps_author_and_current_point_as_tags(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tags.sqlite3"
            initialize(path)
            salt, digest = hash_password("correct horse battery staple")
            with connect(path) as connection:
                user_id = connection.execute(
                    "INSERT INTO users(username,password_salt,password_hash) VALUES (?,?,?)", ("author", salt, digest)
                ).lastrowid
                author_point = connection.execute(
                    "INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES ('user-1','user','author',1,1,1,1,1,1)"
                ).lastrowid
                connection.execute("INSERT INTO profiles(user_id,point_id) VALUES (?,?)", (user_id, author_point))
                users_point = connection.execute("SELECT id FROM points WHERE slug = 'users'").fetchone()[0]
                result = object.__new__(Handler)._create_article(connection, user_id, {
                    "title": "Без текста", "body": "", "coordinates": [1, 1, 1, 1, 1, 1], "parentId": "users", "tags": [], "newTags": ["Новый тег"],
                })
                article_id = connection.execute("SELECT id FROM points WHERE slug = ?", (result["id"],)).fetchone()[0]
                links = {tuple(row) for row in connection.execute("SELECT target_point_id,kind FROM point_links WHERE source_point_id = ?", (article_id,))}
                tag_point = connection.execute("SELECT id FROM points WHERE title = 'Новый тег'").fetchone()[0]
                tags_parent = connection.execute("SELECT id FROM points WHERE slug = 'tags'").fetchone()[0]
                tag_links = {tuple(row) for row in connection.execute("SELECT target_point_id,kind FROM point_links WHERE source_point_id = ?", (tag_point,))}
            self.assertEqual(links, {(author_point, "author"), (users_point, "content"), (tag_point, "content")})
            self.assertIn((tags_parent, "content"), tag_links)

    def test_git_wiki_import_updates_only_git_owned_articles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wiki = root / "wiki"; wiki.mkdir()
            (wiki / "index.md").write_text(
                "---\nid: home\ntitle: Из Git\ncoordinates: [5, 5, 5, 5, 5, 5]\nhome: true\n---\n[Справка](guide.md)\n",
                encoding="utf-8",
            )
            (wiki / "guide.md").write_text(
                "---\nid: guide\ntitle: Справка\ncoordinates: [1, 2, 3, 4, 5, 6]\n---\nТекст.\n",
                encoding="utf-8",
            )
            path = root / "test.sqlite3"; initialize(path)
            with connect(path) as connection:
                user_point = connection.execute(
                    "INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES ('post-local','article','Локальный',1,1,1,1,1,1)"
                ).lastrowid
                self.assertEqual(sync_repository_wiki(connection, root), 2)
                home = connection.execute("SELECT title,system_body,source_path FROM points WHERE slug='home'").fetchone()
                guide = connection.execute("SELECT source_path FROM points WHERE slug='guide'").fetchone()
                links = connection.execute(
                    "SELECT target_point_id FROM point_links WHERE source_point_id=(SELECT id FROM points WHERE slug='home')"
                ).fetchall()
                self.assertEqual(home["title"], "Из Git")
                self.assertIn("[[guide|Справка]]", home["system_body"])
                self.assertEqual(home["source_path"], "wiki/index.md")
                self.assertEqual(guide["source_path"], "wiki/guide.md")
                self.assertEqual([row[0] for row in links], [connection.execute("SELECT id FROM points WHERE slug='guide'").fetchone()[0]])
                self.assertEqual(connection.execute("SELECT title FROM points WHERE id=?", (user_point,)).fetchone()[0], "Локальный")

    def test_git_wiki_rejects_collision_with_user_article(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); wiki = root / "wiki"; wiki.mkdir()
            (wiki / "index.md").write_text("---\nid: home\ntitle: Главная\ncoordinates: [1, 1, 1, 1, 1, 1]\n---\n", encoding="utf-8")
            (wiki / "taken.md").write_text("---\nid: taken\ntitle: Занято\ncoordinates: [1, 1, 1, 1, 1, 1]\n---\n", encoding="utf-8")
            path = root / "test.sqlite3"; initialize(path)
            with connect(path) as connection:
                connection.execute("INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES ('taken','article','Локальная',1,1,1,1,1,1)")
                with self.assertRaises(GitWikiError):
                    sync_repository_wiki(connection, root)


if __name__ == "__main__":
    unittest.main()
