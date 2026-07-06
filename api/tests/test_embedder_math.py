import numpy as np

from app.ml.embedder import l2_normalize, mean_pool


def test_mean_pool_masks_padding():
    # batch=1, seq=3, dim=2; third token is padding and must not count
    tokens = np.array([[[1.0, 2.0], [3.0, 4.0], [100.0, 100.0]]])
    mask = np.array([[1, 1, 0]])
    pooled = mean_pool(tokens, mask)
    assert np.allclose(pooled, [[2.0, 3.0]])


def test_mean_pool_all_masked_is_finite():
    tokens = np.ones((1, 2, 3))
    mask = np.zeros((1, 2))
    pooled = mean_pool(tokens, mask)
    assert np.all(np.isfinite(pooled))


def test_l2_normalize_unit_norm():
    vectors = np.array([[3.0, 4.0], [0.1, 0.0]])
    normed = l2_normalize(vectors)
    assert np.allclose(np.linalg.norm(normed, axis=1), 1.0)
    assert np.allclose(normed[0], [0.6, 0.8])


def test_l2_normalize_zero_vector_is_finite():
    normed = l2_normalize(np.zeros((1, 4)))
    assert np.all(np.isfinite(normed))
