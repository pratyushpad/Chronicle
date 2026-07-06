from app.search.rrf import RRF_K, rrf_fuse


def test_k60_math():
    # id 1: rank 1 in both lists -> 2/(60+1); id 2: rank 2 in one -> 1/62
    fused = rrf_fuse([[1, 2], [1]])
    assert fused == [1, 2]
    assert RRF_K == 60


def test_item_in_both_lists_beats_single_list_top():
    # 3 is rank 2 in both (2/62 ≈ 0.0323); 1 and 2 are rank 1 in one (1/61 ≈ 0.0164)
    fused = rrf_fuse([[1, 3], [2, 3]])
    assert fused[0] == 3


def test_disjoint_lists_interleave_by_rank():
    fused = rrf_fuse([[1, 2], [3, 4]])
    # equal scores at each rank; earlier list wins ties
    assert fused == [1, 3, 2, 4]


def test_single_list_preserves_order():
    assert rrf_fuse([[5, 9, 2]]) == [5, 9, 2]


def test_empty_inputs():
    assert rrf_fuse([]) == []
    assert rrf_fuse([[], []]) == []


def test_deterministic_ties():
    a = rrf_fuse([[1, 2, 3], [4, 5, 6]])
    b = rrf_fuse([[1, 2, 3], [4, 5, 6]])
    assert a == b
