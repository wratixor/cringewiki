"""Build the browser index from current SQLite state."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .influence import calculate_influence

AXES = [
    {"id": "cringe-base", "positive": "Кринж", "negative": "База"},
    {"id": "funny-serious", "positive": "Смешное", "negative": "Серьёзное"},
    {"id": "repost-new", "positive": "Баян", "negative": "Новинка"},
]


def build_index(connection, current_user_id: int | None = None) -> dict[str, Any]:
    rows = connection.execute(
        """SELECT p.*, a.body, a.author_user_id, a.parent_point_id
           FROM points p LEFT JOIN articles a ON a.point_id = p.id ORDER BY p.id"""
    ).fetchall()
    if not rows:
        return {"formatVersion": "0.1", "engineVersion": "0.1.0-dev", "axes": AXES,
                "homeId": None, "concepts": []}

    user_by_point = {row["point_id"]: row["user_id"] for row in connection.execute("SELECT * FROM profiles")}
    point_by_user = {user_id: point_id for point_id, user_id in user_by_point.items()}
    supports: dict[int, list[int]] = defaultdict(list)
    for row in connection.execute("SELECT user_id, target_point_id FROM supports"):
        supports[row["user_id"]].append(row["target_point_id"])
    weights = calculate_influence(list(user_by_point), supports, user_by_point)

    linked: dict[int, set[int]] = defaultdict(set)
    outgoing: dict[int, list[tuple[str, int]]] = defaultdict(list)
    incoming: dict[int, int] = defaultdict(int)
    for row in connection.execute("SELECT source_point_id, target_point_id FROM point_links"):
        linked[row["source_point_id"]].add(row["target_point_id"])
        linked[row["target_point_id"]].add(row["source_point_id"])
        incoming[row["target_point_id"]] += 1
    for row in connection.execute("SELECT source_point_id, target_point_id, kind FROM point_links"):
        outgoing[row["source_point_id"]].append((row["kind"], row["target_point_id"]))
    for user_id, targets in supports.items():
        source = point_by_user[user_id]
        for target in targets:
            linked[source].add(target)
            linked[target].add(source)
            incoming[target] += 1

    votes: dict[int, list[int]] = defaultdict(lambda: [0] * 6)
    own_votes: dict[int, int] = {}
    for row in connection.execute("SELECT user_id, point_id, pole FROM axis_votes"):
        votes[row["point_id"]][row["pole"]] += 1
        if row["user_id"] == current_user_id:
            own_votes[row["point_id"]] = row["pole"]
    own_supports = set(supports.get(current_user_id or -1, []))

    system_point_id = next((row["id"] for row in rows if row["slug"] == "users"), None)
    user_coordinates = {
        row["id"]: [row[f"c{index}"] + votes[row["id"]][index] for index in range(6)]
        for row in rows if row["kind"] == "user"
    }
    concepts = []
    for row in rows:
        base = [row[f"c{index}"] for index in range(6)]
        coordinates = [base[index] + votes[row["id"]][index] for index in range(6)]
        if row["id"] == system_point_id:
            coordinates = [
                1 + sum(values[index] for values in user_coordinates.values()) / 100 + votes[row["id"]][index]
                for index in range(6)
            ]
        author_ids = [target for kind, target in outgoing[row["id"]] if kind == "author"]
        content_ids = [target for kind, target in outgoing[row["id"]] if kind == "content"]
        parent_id = row["parent_point_id"]
        tag_ids = author_ids + ([parent_id] if parent_id else []) + [target for target in content_ids if target != parent_id]
        concepts.append({
            "id": row["slug"], "pointId": row["id"], "kind": "system" if row["id"] == system_point_id else row["kind"], "title": row["title"],
            "coordinates": coordinates, "body": row["body"] or ("Карта публикаций пользователя." if row["kind"] == "user" else ""),
            "linkedIds": [], "incomingCount": incoming[row["id"]], "weight": weights.get(row["id"], 0.0),
            "actionUrl": row["action_url"],
            "selectedPole": own_votes.get(row["id"]), "supported": row["id"] in own_supports,
            "map": row["kind"] == "user", "tagPointIds": tag_ids,
        })
    slug_by_id = {item["pointId"]: item["id"] for item in concepts}
    for item in concepts:
        item["linkedIds"] = sorted(slug_by_id[value] for value in linked[item["pointId"]] if value in slug_by_id)
        item["tagIds"] = [slug_by_id[value] for value in item["tagPointIds"] if value in slug_by_id]
        del item["tagPointIds"]
    home = max(concepts, key=lambda item: (item["weight"], item["incomingCount"], -item["pointId"]))
    return {
        "formatVersion": "0.1", "engineVersion": "0.1.0-dev", "projection": "paired-balance-preview-v0",
        "axes": AXES, "homeId": home["id"], "concepts": concepts,
        "currentUserPointId": slug_by_id.get(point_by_user.get(current_user_id)),
        "mass": {"users": len(user_by_point), "total": sum(weights.values()), "retention": 0.25},
    }
