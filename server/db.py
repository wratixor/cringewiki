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
  c0 INTEGER NOT NULL CHECK (c0 BETWEEN 1 AND 99),
  c1 INTEGER NOT NULL CHECK (c1 BETWEEN 1 AND 99),
  c2 INTEGER NOT NULL CHECK (c2 BETWEEN 1 AND 99),
  c3 INTEGER NOT NULL CHECK (c3 BETWEEN 1 AND 99),
  c4 INTEGER NOT NULL CHECK (c4 BETWEEN 1 AND 99),
  c5 INTEGER NOT NULL CHECK (c5 BETWEEN 1 AND 99),
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
