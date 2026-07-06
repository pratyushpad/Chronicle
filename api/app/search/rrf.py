"""Reciprocal Rank Fusion for combining ranked result lists."""

RRF_K = 60


def rrf_fuse(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    """Fuse ranked id lists into one ordering by RRF score.

    score(id) = sum over lists containing id of 1 / (k + rank), rank 1-based.
    Ties break by earliest appearance in the earlier list, keeping the
    result deterministic.
    """
    scores: dict[int, float] = {}
    first_seen: dict[int, tuple[int, int]] = {}
    for list_idx, ranking in enumerate(rankings):
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            if item not in first_seen:
                first_seen[item] = (list_idx, rank)
    return sorted(scores, key=lambda item: (-scores[item], first_seen[item]))
