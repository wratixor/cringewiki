"""Create a small fictional Reactor-flavoured demo dataset."""

from __future__ import annotations

from .app import DB_PATH
from .db import connect, initialize
from .security import hash_password

USERS = [("reactor", [45, 60, 65, 35, 70, 30]), ("kotoman", [20, 80, 90, 20, 55, 45]), ("archivarius", [30, 70, 35, 75, 95, 15]), ("newfag", [65, 40, 70, 35, 15, 90]), ("seriouscat", [25, 85, 15, 95, 60, 45])]
ARTICLES = [
    ("benefis-krinzha", "Бенефис кринжа", "Сцена для торжественного признания: **да, это кринж**.\n\nСм. [[detektor-bazy|Детектор базы]] и [[vetka-kommentariev|Ветку комментариев]].", [90, 20, 75, 35, 40, 70], 1),
    ("detektor-bazy", "Детектор базы", "Прибор общественной калибровки. Иногда показывает базу, иногда оператора.\n\nСвязан с [[benefis-krinzha|Бенефисом кринжа]].", [25, 92, 50, 55, 45, 65], 2),
    ("kote-s-reaktora", "Котэ с Реактора", "Котэ не требует обоснований. Это демонстрационная статья, а не архив сообщества.", [15, 88, 96, 18, 72, 40], 2),
    ("vetka-kommentariev", "Ветка комментариев", "Пространство, где исходная тема постепенно становится необязательной.\n\nИногда приводит к [[knopka-bayan|Кнопке «Баян»]].", [55, 48, 82, 42, 65, 55], 4),
    ("knopka-bayan", "Кнопка «Баян»", "Точка памяти: повтор может быть ошибкой, традицией или необходимым контекстом.", [35, 68, 55, 52, 98, 12], 3),
]


def seed(path=DB_PATH) -> bool:
    initialize(path)
    with connect(path) as connection:
        if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return False
        user_ids, point_ids = [], []
        for username, coordinates in USERS:
            salt, digest = hash_password("reactor-demo")
            user_id = connection.execute("INSERT INTO users(username,password_salt,password_hash) VALUES (?,?,?)", (username, salt, digest)).lastrowid
            point_id = connection.execute("INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES (?,?,?,?,?,?,?,?,?)", (f"user-{user_id}", "user", username, *coordinates)).lastrowid
            connection.execute("INSERT INTO profiles VALUES (?,?)", (user_id, point_id))
            user_ids.append(user_id); point_ids.append(point_id)
        article_points = {}
        for slug, title, body, coordinates, author_number in ARTICLES:
            point_id = connection.execute("INSERT INTO points(slug,kind,title,c0,c1,c2,c3,c4,c5) VALUES (?,?,?,?,?,?,?,?,?)", (slug, "article", title, *coordinates)).lastrowid
            author_id = user_ids[author_number - 1]
            connection.execute("INSERT INTO articles(point_id,author_user_id,body) VALUES (?,?,?)", (point_id, author_id, body))
            connection.execute("INSERT INTO point_links VALUES (?,?, 'author')", (point_id, point_ids[author_number - 1]))
            article_points[slug] = point_id
        for source, target in [("benefis-krinzha", "detektor-bazy"), ("benefis-krinzha", "vetka-kommentariev"), ("detektor-bazy", "benefis-krinzha"), ("vetka-kommentariev", "knopka-bayan")]:
            connection.execute("INSERT OR IGNORE INTO point_links VALUES (?,?, 'content')", (article_points[source], article_points[target]))
        targets = [article_points["benefis-krinzha"], article_points["kote-s-reaktora"], article_points["knopka-bayan"], point_ids[0], point_ids[1]]
        for user_id, target in zip(user_ids, targets):
            connection.execute("INSERT INTO supports VALUES (?,?)", (user_id, target))
        connection.execute("INSERT INTO supports VALUES (?,?)", (user_ids[0], point_ids[1]))
        connection.execute("INSERT INTO supports VALUES (?,?)", (user_ids[1], point_ids[0]))
    return True


if __name__ == "__main__":
    print("Демо-данные созданы." if seed() else "База уже не пуста; ничего не изменено.")
