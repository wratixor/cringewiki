"""Conserving influence propagation."""

from __future__ import annotations


def calculate_influence(
    user_point_ids: list[int],
    supports: dict[int, list[int]],
    user_by_point: dict[int, int],
    *,
    retention: float = 0.25,
    tolerance: float = 1e-12,
    max_steps: int = 512,
) -> dict[int, float]:
    """Distribute one unit per user without creating mass in cycles.

    At every user point, ``retention`` is absorbed by that point. The rest is
    divided over supports. Article points absorb everything they receive.
    """
    if not 0 < retention <= 1:
        raise ValueError("retention must be in (0, 1]")
    weights: dict[int, float] = {}
    pending = {point_id: 1.0 for point_id in user_point_ids}
    for _ in range(max_steps):
        if sum(pending.values()) <= tolerance:
            break
        next_pending: dict[int, float] = {}
        for source_point, mass in pending.items():
            targets = supports.get(user_by_point[source_point], [])
            if not targets:
                weights[source_point] = weights.get(source_point, 0.0) + mass
                continue
            kept = mass * retention
            weights[source_point] = weights.get(source_point, 0.0) + kept
            share = (mass - kept) / len(targets)
            for target in targets:
                if target in user_by_point:
                    next_pending[target] = next_pending.get(target, 0.0) + share
                else:
                    weights[target] = weights.get(target, 0.0) + share
        pending = next_pending
    # Numerical residue is absorbed at its current user point.
    for point_id, mass in pending.items():
        weights[point_id] = weights.get(point_id, 0.0) + mass
    return weights
