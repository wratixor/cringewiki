"""Dependency-free HTTP and JSON API server for Cringewiki."""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .db import connect, initialize
from .index import build_index
from .security import hash_password, new_token, token_digest, verify_password

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("CRINGEWIKI_DB", ROOT / "var" / "cringewiki.sqlite3"))
SESSION_COOKIE = "cringewiki_session"
USERNAME = re.compile(r"^[\w.-]{3,32}$", re.UNICODE)
INTERNAL_LINK = re.compile(r"\[\[([a-z0-9][a-z0-9-]{0,63})(?:\|[^\]]+)?\]\]")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


class Handler(SimpleHTTPRequestHandler):
    server_version = "Cringewiki/0.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def translate_path(self, path):
        """Expose only files below /web/, never the repository or database."""
        request_path = unquote(urlparse(path).path)
        if not request_path.startswith("/web/"):
            return str(ROOT / "web" / "__not_found__")
        relative = request_path.removeprefix("/web/")
        parts = [part for part in relative.split("/") if part and part not in (".", "..")]
        return str((ROOT / "web").joinpath(*parts))

    def log_message(self, format, *args):
        super().log_message(format, *args)

    def _json(self, payload, status=200, headers=None):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers or []:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ApiError(400, "Некорректный размер запроса") from error
        if not 0 < size <= 262_144:
            raise ApiError(413, "Запрос пуст или слишком велик")
        try:
            return json.loads(self.rfile.read(size))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ApiError(400, "Ожидался JSON") from error

    def _cookie_token(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie[SESSION_COOKIE].value if SESSION_COOKIE in cookie else None

    def _session(self, connection, create=False):
        now = int(time.time())
        connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        token = self._cookie_token()
        if token:
            row = connection.execute("SELECT * FROM sessions WHERE token_hash = ?", (token_digest(token),)).fetchone()
            if row:
                return row, None
        if not create:
            return None, None
        token, csrf = new_token(), new_token()
        connection.execute(
            "INSERT INTO sessions(token_hash, user_id, csrf_token, expires_at) VALUES (?, NULL, ?, ?)",
            (token_digest(token), csrf, now + 7200),
        )
        secure = "; Secure" if os.environ.get("CRINGEWIKI_SECURE_COOKIES") == "1" else ""
        header = ("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000{secure}")
        return connection.execute("SELECT * FROM sessions WHERE token_hash = ?", (token_digest(token),)).fetchone(), header

    def _require_csrf(self, session):
        if not session or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf_token"]):
            raise ApiError(403, "Проверка CSRF не пройдена")

    def _require_user(self, session):
        if not session or session["user_id"] is None:
            raise ApiError(401, "Сначала войдите")
        return session["user_id"]

    @staticmethod
    def _coordinates(data):
        values = data.get("coordinates")
        if not isinstance(values, list) or len(values) != 6 or any(type(value) is not int or not 1 <= value <= 99 for value in values):
            raise ApiError(400, "Нужны шесть целых координат от 1 до 99")
        return values

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/web"):
            self.send_response(302); self.send_header("Location", "/web/"); self.end_headers(); return
        if path.startswith("/api/"):
            try:
                with connect(DB_PATH) as connection:
                    session, header = self._session(connection, create=True)
                    if path == "/api/session":
                        user = None
                        if session["user_id"] is not None:
                            user = dict(connection.execute("SELECT id, username FROM users WHERE id = ?", (session["user_id"],)).fetchone())
                        self._json({"user": user, "csrfToken": session["csrf_token"]}, headers=[header] if header else None)
                    elif path == "/api/index":
                        self._json(build_index(connection, session["user_id"]), headers=[header] if header else None)
                    else:
                        raise ApiError(404, "Маршрут не найден")
            except ApiError as error:
                self._json({"error": error.message}, error.status)
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._read_json()
            with connect(DB_PATH) as connection:
                session, header = self._session(connection, create=True)
                self._require_csrf(session)
                if path == "/api/register":
                    result = self._register(connection, session, data)
                elif path == "/api/login":
                    result = self._login(connection, session, data)
                elif path == "/api/logout":
                    connection.execute("UPDATE sessions SET user_id = NULL, expires_at = ? WHERE token_hash = ?", (int(time.time()) + 7200, session["token_hash"]))
                    result = {"ok": True}
                elif path == "/api/articles":
                    result = self._create_article(connection, self._require_user(session), data)
                elif match := re.fullmatch(r"/api/points/([^/]+)/(vote|support)", path):
                    user_id = self._require_user(session)
                    result = self._point_action(connection, user_id, unquote(match.group(1)), match.group(2), data)
                else:
                    raise ApiError(404, "Маршрут не найден")
                self._json(result, headers=[header] if header else None)
        except ApiError as error:
            self._json({"error": error.message}, error.status)
        except Exception as error:
            self.log_error("Unhandled API error: %r", error)
            self._json({"error": "Внутренняя ошибка сервера"}, 500)

    def _register(self, connection, session, data):
        username, password = str(data.get("username", "")).strip(), str(data.get("password", ""))
        if not USERNAME.fullmatch(username):
            raise ApiError(400, "Логин: 3–32 буквы, цифры, точка, дефис или подчёркивание")
        if len(password) < 8:
            raise ApiError(400, "Пароль должен содержать не менее 8 символов")
        coordinates = self._coordinates(data)
        salt, digest = hash_password(password)
        try:
            cursor = connection.execute("INSERT INTO users(username,password_salt,password_hash) VALUES (?,?,?)", (username, salt, digest))
            user_id = cursor.lastrowid
            point = connection.execute(
                "INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES (?,?,?,?,?,?,?,?,?)",
                (f"user-{user_id}", "user", username, *coordinates),
            ).lastrowid
            connection.execute("INSERT INTO profiles(user_id,point_id) VALUES (?,?)", (user_id, point))
            connection.execute("UPDATE sessions SET user_id = ?, expires_at = ? WHERE token_hash = ?", (user_id, int(time.time()) + 2592000, session["token_hash"]))
        except Exception as error:
            if "UNIQUE" in str(error):
                raise ApiError(409, "Такой логин уже занят") from error
            raise
        return {"user": {"id": user_id, "username": username}}

    def _login(self, connection, session, data):
        username, password = str(data.get("username", "")).strip(), str(data.get("password", ""))
        row = connection.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        if not row or not verify_password(password, row["password_salt"], row["password_hash"]):
            raise ApiError(401, "Неверный логин или пароль")
        connection.execute("UPDATE sessions SET user_id = ?, expires_at = ? WHERE token_hash = ?", (row["id"], int(time.time()) + 2592000, session["token_hash"]))
        return {"user": {"id": row["id"], "username": row["username"]}}

    def _create_article(self, connection, user_id, data):
        title, body = str(data.get("title", "")).strip(), str(data.get("body", "")).strip()
        if not 1 <= len(title) <= 128 or not 1 <= len(body) <= 100000:
            raise ApiError(400, "Заголовок 1–128 символов, текст 1–100000 символов")
        coordinates = self._coordinates(data)
        cap = int(os.environ.get("CRINGEWIKI_MAX_ARTICLES_PER_USER", "99"))
        count = connection.execute("SELECT COUNT(*) FROM articles WHERE author_user_id = ?", (user_id,)).fetchone()[0]
        if count >= cap:
            raise ApiError(409, f"Достигнут лимит: {cap} публикаций")
        slug = f"post-{secrets.token_hex(8)}"
        point_id = connection.execute(
            "INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES (?,?,?,?,?,?,?,?,?)",
            (slug, "article", title, *coordinates),
        ).lastrowid
        connection.execute("INSERT INTO articles(point_id,author_user_id,body) VALUES (?,?,?)", (point_id, user_id, body))
        author_point = connection.execute("SELECT point_id FROM profiles WHERE user_id = ?", (user_id,)).fetchone()[0]
        connection.execute("INSERT INTO point_links VALUES (?,?, 'author')", (point_id, author_point))
        for target_slug in set(INTERNAL_LINK.findall(body)):
            target = connection.execute("SELECT id FROM points WHERE slug = ?", (target_slug,)).fetchone()
            if target and target[0] != point_id:
                connection.execute("INSERT OR IGNORE INTO point_links VALUES (?,?, 'content')", (point_id, target[0]))
        return {"id": slug}

    def _point_action(self, connection, user_id, slug, action, data):
        point = connection.execute("SELECT id FROM points WHERE slug = ?", (slug,)).fetchone()
        if not point:
            raise ApiError(404, "Точка не найдена")
        if action == "vote":
            pole = data.get("pole")
            if type(pole) is not int or not 0 <= pole <= 5:
                raise ApiError(400, "Полюс должен быть от 0 до 5")
            connection.execute("INSERT INTO axis_votes VALUES (?,?,?) ON CONFLICT(user_id,point_id) DO UPDATE SET pole=excluded.pole", (user_id, point[0], pole))
            return {"selectedPole": pole}
        enabled = bool(data.get("enabled", True))
        if enabled:
            connection.execute("INSERT OR IGNORE INTO supports VALUES (?,?)", (user_id, point[0]))
        else:
            connection.execute("DELETE FROM supports WHERE user_id=? AND target_point_id=?", (user_id, point[0]))
        return {"supported": enabled}


def main():
    initialize(DB_PATH)
    host = os.environ.get("CRINGEWIKI_HOST", "127.0.0.1")
    port = int(os.environ.get("CRINGEWIKI_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Cringewiki: http://{host}:{port}/web/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
