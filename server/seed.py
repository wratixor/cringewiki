"""Create a small fictional Reactor-flavoured demo dataset."""

from __future__ import annotations

from .app import DB_PATH
from .db import connect, initialize
from .security import hash_password

USERS = [("reactor", [5, 6, 7, 4, 7, 3]), ("kotoman", [2, 8, 9, 2, 6, 5]), ("archivarius", [3, 7, 4, 8, 10, 2]), ("newfag", [7, 4, 7, 4, 2, 9]), ("seriouscat", [3, 9, 2, 10, 6, 5])]
ARTICLES = [
    ("benefis-krinzha", "Бенефис кринжа", "Сцена для торжественного признания: **да, это кринж**.\n\nСм. [[detektor-bazy|Детектор базы]] и [[vetka-kommentariev|Ветку комментариев]].", [9, 2, 8, 4, 4, 7], 1),
    ("detektor-bazy", "Детектор базы", "Прибор общественной калибровки. Иногда показывает базу, иногда оператора.\n\nСвязан с [[benefis-krinzha|Бенефисом кринжа]].", [3, 9, 5, 6, 5, 7], 2),
    ("kote-s-reaktora", "Котэ с Реактора", "Котэ не требует обоснований. Это демонстрационная статья, а не архив сообщества.", [2, 9, 10, 2, 7, 4], 2),
    ("vetka-kommentariev", "Ветка комментариев", "Пространство, где исходная тема постепенно становится необязательной.\n\nИногда приводит к [[knopka-bayan|Кнопке «Баян»]].", [6, 5, 8, 4, 7, 6], 4),
    ("knopka-bayan", "Кнопка «Баян»", "Точка памяти: повтор может быть ошибкой, традицией или необходимым контекстом.", [4, 7, 6, 6, 10, 2], 3),
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
