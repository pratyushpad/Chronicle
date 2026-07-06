import random

from app.eval.metrics import mrr, ndcg_at_k, recall_at_k
from scripts.eval_matching import sample_negatives


# ── hand-computed metric values ───────────────────────────────────────────────

def test_recall_at_k():
    assert recall_at_k([1, 2, 3, 4], {1, 4}, k=2) == 0.5
    assert recall_at_k([1, 2, 3, 4], {1, 4}, k=4) == 1.0
    assert recall_at_k([5, 6], {1}, k=2) == 0.0
    assert recall_at_k([1], set(), k=2) == 0.0


def test_ndcg_at_k_perfect_ranking_is_one():
    assert ndcg_at_k([1, 2, 9, 8], {1, 2}, k=4) == 1.0


def test_ndcg_at_k_hand_value():
    # relevant at ranks 1 and 3: dcg = 1/log2(2) + 1/log2(4) = 1.5
    # ideal (2 relevant): 1/log2(2) + 1/log2(3) ≈ 1.6309
    import math

    got = ndcg_at_k([1, 9, 2], {1, 2}, k=3)
    expected = (1.0 + 1.0 / math.log2(4)) / (1.0 + 1.0 / math.log2(3))
    assert abs(got - expected) < 1e-9


def test_ndcg_empty_relevant():
    assert ndcg_at_k([1, 2], set(), k=2) == 0.0


def test_mrr():
    assert mrr([9, 8, 1], {1}) == 1.0 / 3
    assert mrr([1, 2], {1, 2}) == 1.0
    assert mrr([9, 8], {1}) == 0.0


# ── determinism + sampler ─────────────────────────────────────────────────────

def test_holdout_split_deterministic():
    ids = list(range(100))
    a = random.Random(42).sample(ids, 30)
    b = random.Random(42).sample(ids, 30)
    assert a == b


def test_sample_negatives_excludes_engaged():
    rng = random.Random(7)
    pool = list(range(50))
    engaged = {0, 1, 2, 3, 4}
    negs = sample_negatives(rng, pool, engaged, 20)
    assert len(negs) == 20
    assert not engaged & set(negs)


def test_sample_negatives_small_pool_returns_all_eligible():
    rng = random.Random(7)
    negs = sample_negatives(rng, [1, 2, 3], {2}, 20)
    assert negs == [1, 3]


def test_sample_negatives_deterministic():
    a = sample_negatives(random.Random(11), list(range(200)), {5}, 30)
    b = sample_negatives(random.Random(11), list(range(200)), {5}, 30)
    assert a == b
