"""Offline ranking metrics — pure functions over id lists.

`ranking` is job ids ordered best-first; `relevant` is the ground-truth
positive set. Binary relevance throughout.
"""
import math


def recall_at_k(ranking: list[int], relevant: set[int], k: int) -> float:
    """Fraction of relevant items appearing in the top k."""
    if not relevant:
        return 0.0
    hits = sum(1 for item in ranking[:k] if item in relevant)
    return hits / len(relevant)


def ndcg_at_k(ranking: list[int], relevant: set[int], k: int) -> float:
    """Normalized discounted cumulative gain with binary gains."""
    if not relevant:
        return 0.0
    dcg = sum(
        1.0 / math.log2(i + 2)
        for i, item in enumerate(ranking[:k])
        if item in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


def mrr(ranking: list[int], relevant: set[int]) -> float:
    """Reciprocal rank of the first relevant item (0 when none appear)."""
    for i, item in enumerate(ranking, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0
