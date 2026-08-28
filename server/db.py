"""SQLite persistence for the minimal Cringewiki server."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL COLLATE NOCASE UNIQUE,
  password_salt BLOB NOT NULL,
  password_hash BLOB NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS points (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL CHECK (kind IN ('user', 'article')),
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 128),
  action_url TEXT,
  source_path TEXT,
  system_body TEXT NOT NULL DEFAULT '' CHECK (length(system_body) <= 100000),
  c0 INTEGER NOT NULL CHECK (c0 BETWEEN 1 AND 10),
  c1 INTEGER NOT NULL CHECK (c1 BETWEEN 1 AND 10),
  c2 INTEGER NOT NULL CHECK (c2 BETWEEN 1 AND 10),
  c3 INTEGER NOT NULL CHECK (c3 BETWEEN 1 AND 10),
  c4 INTEGER NOT NULL CHECK (c4 BETWEEN 1 AND 10),
  c5 INTEGER NOT NULL CHECK (c5 BETWEEN 1 AND 10),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS profiles (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  point_id INTEGER NOT NULL UNIQUE REFERENCES points(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY,
  point_id INTEGER NOT NULL UNIQUE REFERENCES points(id) ON DELETE CASCADE,
  author_user_id INTEGER NOT NULL REFERENCES users(id),
  parent_point_id INTEGER REFERENCES points(id),
  body TEXT NOT NULL CHECK (length(body) <= 100000),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS point_links (
  source_point_id INTEGER NOT NULL REFERENCES points(id) ON DELETE CASCADE,
  target_point_id INTEGER NOT NULL REFERENCES points(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('content', 'author')),
  PRIMARY KEY (source_point_id, target_point_id, kind),
  CHECK (source_point_id <> target_point_id)
);
CREATE TABLE IF NOT EXISTS supports (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  target_point_id INTEGER NOT NULL REFERENCES points(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, target_point_id)
);
CREATE TABLE IF NOT EXISTS axis_votes (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  point_id INTEGER NOT NULL REFERENCES points(id) ON DELETE CASCADE,
  pole INTEGER NOT NULL CHECK (pole BETWEEN 0 AND 5),
  PRIMARY KEY (user_id, point_id)
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash BLOB PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  csrf_token TEXT NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS point_links_target ON point_links(target_point_id);
CREATE INDEX IF NOT EXISTS supports_target ON supports(target_point_id);
"""

COORDINATE_GUARDS = """
CREATE TRIGGER IF NOT EXISTS points_coordinates_insert
BEFORE INSERT ON points
WHEN NEW.c0 NOT BETWEEN 1 AND 10 OR NEW.c1 NOT BETWEEN 1 AND 10
  OR NEW.c2 NOT BETWEEN 1 AND 10 OR NEW.c3 NOT BETWEEN 1 AND 10
  OR NEW.c4 NOT BETWEEN 1 AND 10 OR NEW.c5 NOT BETWEEN 1 AND 10
BEGIN SELECT RAISE(ABORT, 'base coordinates must be between 1 and 10'); END;
CREATE TRIGGER IF NOT EXISTS points_coordinates_update
BEFORE UPDATE OF c0, c1, c2, c3, c4, c5 ON points
WHEN NEW.c0 NOT BETWEEN 1 AND 10 OR NEW.c1 NOT BETWEEN 1 AND 10
  OR NEW.c2 NOT BETWEEN 1 AND 10 OR NEW.c3 NOT BETWEEN 1 AND 10
  OR NEW.c4 NOT BETWEEN 1 AND 10 OR NEW.c5 NOT BETWEEN 1 AND 10
BEGIN SELECT RAISE(ABORT, 'base coordinates must be between 1 and 10'); END;
"""


class ClosingConnection(sqlite3.Connection):
    """A transaction context which also releases the file handle on exit."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize(path: Path) -> None:
    with connect(path) as connection:
        connection.executescript(SCHEMA)
        point_columns = {row[1] for row in connection.execute("PRAGMA table_info(points)")}
        if "action_url" not in point_columns:
            connection.execute("ALTER TABLE points ADD COLUMN action_url TEXT")
        if "source_path" not in point_columns:
            connection.execute("ALTER TABLE points ADD COLUMN source_path TEXT")
        if "system_body" not in point_columns:
            connection.execute("ALTER TABLE points ADD COLUMN system_body TEXT NOT NULL DEFAULT ''")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS points_source_path ON points(source_path) WHERE source_path IS NOT NULL")
        article_columns = {row[1] for row in connection.execute("PRAGMA table_info(articles)")}
        if "parent_point_id" not in article_columns:
            connection.execute("ALTER TABLE articles ADD COLUMN parent_point_id INTEGER REFERENCES points(id)")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            columns = ", ".join(
                f"c{index} = MAX(1, MIN(10, ROUND(1 + (c{index} - 1) * 9.0 / 98)))"
                for index in range(6)
            )
            connection.execute(f"UPDATE points SET {columns}")
            connection.execute("PRAGMA user_version = 1")
        connection.executescript(COORDINATE_GUARDS)
        ensure_users_concept(connection)
        ensure_tags_concept(connection)
        ensure_home_concept(connection)
        ensure_rickroll_concept(connection)
        ensure_home_links(connection)


def ensure_users_concept(connection: sqlite3.Connection) -> int:
    """Create the system tag and link every user point to it."""
    row = connection.execute("SELECT id FROM points WHERE slug = 'users'").fetchone()
    if row:
        point_id = row[0]
    else:
        point_id = connection.execute(
            "INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES ('users','article','Пользователи',1,1,1,1,1,1)"
        ).lastrowid
    connection.execute(
        """INSERT OR IGNORE INTO point_links(source_point_id,target_point_id,kind)
           SELECT point_id, ?, 'content' FROM profiles WHERE point_id <> ?""",
        (point_id, point_id),
    )
    return point_id


def ensure_tags_concept(connection: sqlite3.Connection) -> int:
    """Create the common parent for tag concepts."""
    row = connection.execute("SELECT id FROM points WHERE slug = 'tags'").fetchone()
    if row:
        return row[0]
    return connection.execute(
        "INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES ('tags','article','Теги',1,1,1,1,1,1)"
    ).lastrowid


HOME_BODY = "# Кринжевики\n\nОткрытая карта реакторского знания. Начните с [[users|Пользователей]], [[tags|Тегов]] или [[rickroll|Рикролла]]."
RICKROLL_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
RICKROLL_BODY = "![Кадр из клипа](https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg)\n\nТочка, которая обещает навигацию, а открывает классический клип."


def _ensure_system_point(connection: sqlite3.Connection, slug: str, title: str, coordinates: tuple[int, ...], body: str = "", action_url: str | None = None) -> int:
    row = connection.execute("SELECT id FROM points WHERE slug = ?", (slug,)).fetchone()
    if row:
        connection.execute("UPDATE points SET title = ?, system_body = ?, action_url = ? WHERE id = ?", (title, body, action_url, row[0]))
        return row[0]
    return connection.execute(
        "INSERT INTO points(slug,kind,title,action_url,system_body,c0,c1,c2,c3,c4,c5) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (slug, "article", title, action_url, body, *coordinates),
    ).lastrowid


def ensure_home_concept(connection: sqlite3.Connection) -> int:
    return _ensure_system_point(connection, "home", "Главная", (5, 5, 5, 5, 5, 5), HOME_BODY)


def ensure_rickroll_concept(connection: sqlite3.Connection) -> int:
    return _ensure_system_point(connection, "rickroll", "Рикролл", (8, 2, 9, 2, 10, 2), RICKROLL_BODY, RICKROLL_URL)


def ensure_home_links(connection: sqlite3.Connection) -> None:
    home = connection.execute("SELECT id FROM points WHERE slug = 'home'").fetchone()[0]
    for slug in ("users", "tags", "rickroll"):
        target = connection.execute("SELECT id FROM points WHERE slug = ?", (slug,)).fetchone()[0]
        connection.execute("INSERT OR IGNORE INTO point_links VALUES (?, ?, 'content')", (home, target))
