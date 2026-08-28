"""Import repository-owned Markdown articles into the local Cringewiki store.

The importer deliberately has a narrow boundary: it only owns rows marked with
``source_path``.  Browser-created articles remain in SQLite and are never
overwritten by a Git update.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .db import RICKROLL_URL, connect, initialize

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MARKDOWN_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
INTERNAL_LINK = re.compile(r"\[\[([a-z0-9][a-z0-9-]{0,63})(?:\|[^\]]+)?\]\]")
RESERVED_IDS = {"users", "tags"}


class GitWikiError(ValueError):
    """The committed wiki source is invalid and must not be imported."""


@dataclass(frozen=True)
class SourceArticle:
    identifier: str
    title: str
    coordinates: tuple[int, int, int, int, int, int]
    path: Path
    body: str


def _parse_article(path: Path, wiki_root: Path) -> SourceArticle:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise GitWikiError(f"wiki/{path.relative_to(wiki_root)}: нет открывающего блока метаданных")
    try:
        closing = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as error:
        raise GitWikiError(f"wiki/{path.relative_to(wiki_root)}: нет закрывающего блока метаданных") from error
    metadata: dict[str, str] = {}
    for number, line in enumerate(lines[1:closing], 2):
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip() or key.strip() in metadata:
            raise GitWikiError(f"wiki/{path.relative_to(wiki_root)}:{number}: ожидается уникальная запись key: value")
        metadata[key.strip()] = value.strip()
    unknown = set(metadata) - {"id", "title", "coordinates", "home", "map"}
    missing = {"id", "title", "coordinates"} - set(metadata)
    if unknown or missing:
        details = ", ".join(sorted(unknown or missing))
        raise GitWikiError(f"wiki/{path.relative_to(wiki_root)}: некорректные метаданные ({details})")
    identifier, title = metadata["id"], metadata["title"].strip()
    if not ID_PATTERN.fullmatch(identifier) or identifier in RESERVED_IDS:
        raise GitWikiError(f"wiki/{path.relative_to(wiki_root)}: недопустимый id {identifier!r}")
    if not 1 <= len(title) <= 128:
        raise GitWikiError(f"wiki/{path.relative_to(wiki_root)}: заголовок должен содержать 1–128 символов")
    try:
        raw_coordinates = json.loads(metadata["coordinates"])
    except json.JSONDecodeError as error:
        raise GitWikiError(f"wiki/{path.relative_to(wiki_root)}: coordinates должен быть JSON-массивом") from error
    if (not isinstance(raw_coordinates, list) or len(raw_coordinates) != 6
            or any(type(value) is not int or not 1 <= value <= 10 for value in raw_coordinates)):
        raise GitWikiError(f"wiki/{path.relative_to(wiki_root)}: нужны шесть целых координат от 1 до 10")
    return SourceArticle(identifier, title, tuple(raw_coordinates), path.relative_to(wiki_root), "\n".join(lines[closing + 1:]).strip())


def _collect(wiki_root: Path) -> tuple[list[SourceArticle], dict[Path, SourceArticle]]:
    files = sorted(wiki_root.rglob("*.md")) if wiki_root.exists() else []
    if not files:
        raise GitWikiError("wiki/ не содержит Markdown-статей")
    articles = [_parse_article(path, wiki_root) for path in files]
    by_id: dict[str, SourceArticle] = {}
    by_path: dict[Path, SourceArticle] = {}
    for article in articles:
        if article.identifier in by_id:
            raise GitWikiError(f"повторяющийся id статьи: {article.identifier}")
        by_id[article.identifier] = article
        by_path[article.path] = article
    homes = [article for article in articles if article.identifier == "home"]
    if len(homes) != 1:
        raise GitWikiError("в wiki/ должна быть ровно одна главная статья с id: home")
    return articles, by_path


def _rewrite_body(article: SourceArticle, by_path: dict[Path, SourceArticle], wiki_root: Path) -> tuple[str, set[str]]:
    links: set[str] = set(INTERNAL_LINK.findall(article.body))

    def replace(match: re.Match[str]) -> str:
        label, href = match.group(1).strip(), match.group(2).strip()
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or not parsed.path:
            return match.group(0)
        candidate = (wiki_root / article.path.parent / unquote(parsed.path)).resolve()
        root = wiki_root.resolve()
        if candidate != root and root not in candidate.parents:
            raise GitWikiError(f"wiki/{article.path}: ссылка выходит за пределы wiki/: {href}")
        target = by_path.get(candidate.relative_to(root))
        if target is None:
            raise GitWikiError(f"wiki/{article.path}: не найдена статья по ссылке {href}")
        if target.identifier != article.identifier:
            links.add(target.identifier)
        return f"[[{target.identifier}|{label}]]"

    body = MARKDOWN_LINK.sub(replace, article.body)
    return body, links - {article.identifier}


def sync_repository_wiki(connection: sqlite3.Connection, repository_root: Path) -> int:
    """Synchronise only Git-owned wiki rows and their outgoing content links."""
    wiki_root = repository_root / "wiki"
    articles, by_path = _collect(wiki_root)
    rewritten = {article.identifier: _rewrite_body(article, by_path, wiki_root) for article in articles}
    count = 0
    for article in articles:
        source_path = f"wiki/{article.path.as_posix()}"
        existing = connection.execute("SELECT id, source_path FROM points WHERE slug = ?", (article.identifier,)).fetchone()
        if existing and existing["source_path"] not in (None, source_path):
            raise GitWikiError(f"id {article.identifier!r} уже принадлежит другой Git-статье")
        if existing and existing["source_path"] is None and article.identifier not in {"home", "rickroll"}:
            raise GitWikiError(f"id {article.identifier!r} уже занят пользовательской или системной точкой")
        body, _ = rewritten[article.identifier]
        action_url = RICKROLL_URL if article.identifier == "rickroll" else None
        if existing:
            connection.execute(
                "UPDATE points SET kind='article', title=?, source_path=?, system_body=?, action_url=?, c0=?,c1=?,c2=?,c3=?,c4=?,c5=? WHERE id=?",
                (article.title, source_path, body, action_url, *article.coordinates, existing["id"]),
            )
        else:
            connection.execute(
                "INSERT INTO points(slug,kind,title,action_url,source_path,system_body,c0,c1,c2,c3,c4,c5) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (article.identifier, "article", article.title, action_url, source_path, body, *article.coordinates),
            )
        count += 1

    source_rows = {row["slug"]: row["id"] for row in connection.execute("SELECT id, slug FROM points WHERE source_path IS NOT NULL")}
    for article in articles:
        source_id = source_rows[article.identifier]
        connection.execute("DELETE FROM point_links WHERE source_point_id = ? AND kind = 'content'", (source_id,))
        _, links = rewritten[article.identifier]
        for target_slug in links:
            target = connection.execute("SELECT id FROM points WHERE slug = ?", (target_slug,)).fetchone()
            if target:
                connection.execute("INSERT OR IGNORE INTO point_links VALUES (?, ?, 'content')", (source_id, target["id"]))
    return count


def main() -> None:
    from .app import DB_PATH, ROOT

    parser = argparse.ArgumentParser(description="Импортировать Git-вики в SQLite")
    parser.add_argument("--database", type=Path, default=DB_PATH)
    parser.add_argument("--repository", type=Path, default=ROOT)
    arguments = parser.parse_args()
    initialize(arguments.database)
    with connect(arguments.database) as connection:
        count = sync_repository_wiki(connection, arguments.repository)
    print(f"Импортировано Git-статей: {count}")


if __name__ == "__main__":
    main()
