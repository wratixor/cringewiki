"""Static-file exposure boundary."""

import unittest
from server.app import Handler, ROOT


class StaticBoundaryTests(unittest.TestCase):
    def translate(self, path):
        handler = object.__new__(Handler)
        return Handler.translate_path(handler, path)

    def test_web_asset_maps_inside_web_root(self):
        self.assertEqual(self.translate("/web/app.js"), str(ROOT / "web" / "app.js"))

    def test_database_and_traversal_do_not_map_to_real_files(self):
        blocked = str(ROOT / "web" / "__not_found__")
        self.assertEqual(self.translate("/var/cringewiki.sqlite3"), blocked)
        self.assertEqual(self.translate("/.git/config"), blocked)
        self.assertEqual(self.translate("/web/../../var/cringewiki.sqlite3"), str(ROOT / "web" / "var" / "cringewiki.sqlite3"))


if __name__ == "__main__":
    unittest.main()
