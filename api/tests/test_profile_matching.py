from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from app.ml.profile_embedding import build_profile_text, combine, weighted_centroid
from app.routers.recommendations import (
    ALPHA_COSINE,
    BETA_RULE,
    RuleContext,
    blend_score,
    rule_score,
)


# ── profile text ──────────────────────────────────────────────────────────────

def test_profile_text_full():
    text = build_profile_text(
        tracks=["ml", "swe"],
        tech_tags=["python", "pytorch"],
        seniority_pref=["new_grad"],
        location="New York, NY",
        headline="ML engineer",
    )
    assert text == (
        "ML engineer. Interested in ml, swe roles. Seniority: new_grad. "
        "Skills: python, pytorch. Based in New York, NY."
    )


def test_profile_text_empty():
    assert build_profile_text(None, None, None, None, None) == ""


# ── centroid math ─────────────────────────────────────────────────────────────

def test_weighted_centroid_weights_applied_higher():
    # applied job at +x (weight 2), saved job at +y (weight 1) → tilts toward x
    vectors = [[1.0, 0.0], [0.0, 1.0]]
    centroid = weighted_centroid(vectors, [2.0, 1.0])
    assert centroid[0] > centroid[1]
    assert np.isclose(np.linalg.norm(centroid), 1.0)


def test_weighted_centroid_empty():
    assert weighted_centroid([], []) is None


def test_combine_fallbacks():
    v = np.array([1.0, 0.0], dtype=np.float32)
    assert combine(None, None) is None
    assert np.allclose(combine(v, None), [1.0, 0.0])
    assert np.allclose(combine(None, v), [1.0, 0.0])
    both = combine(np.array([1.0, 0.0]), np.array([0.0, 1.0]))
    assert np.isclose(np.linalg.norm(both), 1.0)
    assert both[0] == both[1]  # equal 0.5 weights


# ── blend ─────────────────────────────────────────────────────────────────────

def test_blend_score_weights():
    assert blend_score(cosine=1.0, rule_total=5.0, max_rule=5.0) == ALPHA_COSINE + BETA_RULE
    assert blend_score(cosine=0.5, rule_total=0.0, max_rule=5.0) == ALPHA_COSINE * 0.5
    # negative rule scores clamp to zero, never subtract
    assert blend_score(cosine=0.5, rule_total=-3.0, max_rule=5.0) == ALPHA_COSINE * 0.5
    # empty pool (max_rule 0) → pure cosine
    assert blend_score(cosine=0.8, rule_total=2.0, max_rule=0.0) == ALPHA_COSINE * 0.8


# ── rule scorer on plain data (the eval-harness contract) ─────────────────────

@dataclass
class FakeJob:
    title: str = "Software Engineer"
    department: str | None = "Engineering"
    company_id: int = 1
    tech_tags: list[str] | None = None
    experience_level: str | None = None
    location_normalized: str | None = None
    remote: bool | None = None
    sponsorship_flag: str | None = None
    salary_max: int | None = None
    posted_at: datetime | None = None


def test_rule_score_on_plain_object():
    job = FakeJob(
        title="Machine Learning Engineer",
        tech_tags=["python", "pytorch"],
        posted_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    ctx = RuleContext(tracks=["ml"], user_tech=["python"])
    result = rule_score(job, ctx)
    assert result is not None
    total, why = result
    assert total > 0
    assert "Matches your ML track" in why


def test_rule_score_salary_floor_filters():
    job = FakeJob(salary_max=90_000)
    assert rule_score(job, RuleContext(salary_floor=120_000)) is None


def test_rule_score_seniority_penalty():
    job = FakeJob(title="Senior Staff Engineer", experience_level="Senior")
    ctx = RuleContext(tracks=["swe"], seniority_pref=["intern"])
    total, _ = rule_score(job, ctx)
    baseline_ctx = RuleContext(tracks=["swe"])
    baseline_total, _ = rule_score(job, baseline_ctx)
    assert total < baseline_total
