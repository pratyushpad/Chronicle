"""Offline evaluation: rule baseline vs pure semantic vs hybrid blend.

    python -m scripts.eval_matching --seed 42 --mode personas|db|both \
        --output ../docs/eval_results.md

personas mode is DB-free: 5 synthetic personas x 20 labeled-relevant jobs
(api/tests/fixtures/personas.json); each persona's jobs are hard negatives
for the others. 30% of a persona's jobs are held out as "engaged" to build
the profile centroid; the rest are the positives to retrieve.

db mode evaluates real users with >= MIN_ENGAGEMENTS applications: 30% of
their engaged jobs are held out as positives, the rest build the profile
vector, negatives are sampled 20:1 from active never-engaged jobs.

Deterministic under --seed. Reuses the exact production scorers:
rule_score / blend_score (recommendations) and the profile-vector math
(app/ml/profile_embedding).
"""
import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import numpy as np  # noqa: E402

from app.eval.metrics import mrr, ndcg_at_k, recall_at_k  # noqa: E402
from app.ml.profile_embedding import combine, weighted_centroid  # noqa: E402
from app.ml.text import build_embedding_text  # noqa: E402
from app.routers.recommendations import RuleContext, blend_score, rule_score  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "personas.json"
RECALL_K = 50
NDCG_K = 10
HOLDOUT_FRACTION = 0.3
NEGATIVE_RATIO = 20
MIN_ENGAGEMENTS = 5


@dataclass
class EvalJob:
    """Duck-typed stand-in with every field rule_score touches."""

    id: int
    title: str
    department: str | None
    company_id: int
    tech_tags: list[str] | None
    location_normalized: str | None
    remote: bool | None
    experience_level: str | None = None
    sponsorship_flag: str | None = None
    salary_max: int | None = None
    posted_at: datetime | None = None


def _rank(ids_scores: list[tuple[int, float]]) -> list[int]:
    return [i for i, _ in sorted(ids_scores, key=lambda t: (-t[1], t[0]))]


def _metrics(ranking: list[int], relevant: set[int]) -> dict[str, float]:
    return {
        f"recall@{RECALL_K}": recall_at_k(ranking, relevant, RECALL_K),
        f"ndcg@{NDCG_K}": ndcg_at_k(ranking, relevant, NDCG_K),
        "mrr": mrr(ranking, relevant),
    }


def _evaluate_pool(
    candidates: list[EvalJob],
    embeddings: dict[int, np.ndarray],
    profile_vec: np.ndarray | None,
    ctx: RuleContext,
    positives: set[int],
) -> dict[str, dict[str, float]]:
    """Run all three rankers over one candidate pool and score them."""
    rule_totals: dict[int, float] = {}
    for job in candidates:
        result = rule_score(job, ctx)
        rule_totals[job.id] = result[0] if result is not None else float("-inf")
    finite = [v for v in rule_totals.values() if v != float("-inf")]
    max_rule = max(finite, default=0.0)

    cosines = {
        job.id: float(embeddings[job.id] @ profile_vec) if profile_vec is not None else 0.0
        for job in candidates
    }

    rankings = {
        "rule": _rank([(j.id, rule_totals[j.id]) for j in candidates]),
        "semantic": _rank([(j.id, cosines[j.id]) for j in candidates]),
        "hybrid": _rank(
            [
                (
                    j.id,
                    blend_score(
                        cosines[j.id],
                        rule_totals[j.id] if rule_totals[j.id] != float("-inf") else 0.0,
                        max_rule,
                    ),
                )
                for j in candidates
            ]
        ),
    }
    return {name: _metrics(ranking, positives) for name, ranking in rankings.items()}


BOOTSTRAP_SAMPLES = 5000


def _aggregate(
    per_query: list[dict[str, dict[str, float]]], seed: int
) -> dict[str, dict[str, tuple[float, float, float]]]:
    """Mean + bootstrap 95% CI per (ranker, metric) over the per-query scores.

    The CI is a percentile bootstrap that resamples queries with replacement — with a
    handful of personas it is deliberately wide, which is the honest read of the sample
    size. It narrows as the persona/user set grows.
    """
    rng = np.random.default_rng(seed)
    q = len(per_query)
    out: dict[str, dict[str, tuple[float, float, float]]] = {}
    for ranker in ("rule", "semantic", "hybrid"):
        metric_names = per_query[0][ranker].keys()
        out[ranker] = {}
        for m in metric_names:
            vals = np.array([query[ranker][m] for query in per_query], dtype=float)
            mean = float(vals.mean())
            if q > 1:
                idx = rng.integers(0, q, size=(BOOTSTRAP_SAMPLES, q))
                boot_means = vals[idx].mean(axis=1)
                lo, hi = (float(x) for x in np.percentile(boot_means, [2.5, 97.5]))
            else:
                lo = hi = mean
            out[ranker][m] = (mean, lo, hi)
    return out


# ── personas mode ─────────────────────────────────────────────────────────────

def eval_personas(seed: int) -> tuple[dict, int]:
    from app.ml.embedder import get_embedder

    data = json.loads(FIXTURE.read_text())["personas"]

    jobs: list[EvalJob] = []
    owner: dict[int, str] = {}
    texts: list[str] = []
    for persona in data:
        for raw in persona["jobs"]:
            job_id = len(jobs)
            jobs.append(
                EvalJob(
                    id=job_id,
                    title=raw["title"],
                    department=raw.get("department"),
                    company_id=10_000 + job_id,  # no affinity signal in personas mode
                    tech_tags=raw.get("tech_tags"),
                    location_normalized=raw.get("location"),
                    remote=raw.get("location") == "Remote",
                )
            )
            owner[job_id] = persona["name"]
            texts.append(
                build_embedding_text(
                    title=raw["title"],
                    company_name=raw.get("company_name"),
                    department=raw.get("department"),
                    location=raw.get("location"),
                    tech_tags=raw.get("tech_tags"),
                    description_text=raw.get("description"),
                )
            )
    vectors = get_embedder().encode(texts)
    embeddings = {job.id: np.asarray(vectors[job.id], dtype=np.float32) for job in jobs}

    per_persona = []
    for persona in data:
        rng = random.Random(seed)
        own_ids = [j.id for j in jobs if owner[j.id] == persona["name"]]
        n_engaged = max(1, round(len(own_ids) * HOLDOUT_FRACTION))
        engaged = set(rng.sample(sorted(own_ids), n_engaged))
        positives = set(own_ids) - engaged
        candidates = [j for j in jobs if j.id not in engaged]

        profile = persona["profile"]
        text = build_profile_text_from(profile)
        text_vec = np.asarray(get_embedder().encode([text])[0], dtype=np.float32) if text else None
        engaged_sorted = sorted(engaged)
        centroid = weighted_centroid(
            [embeddings[i].tolist() for i in engaged_sorted],
            # first engagement counts as an application (2x), rest as saves
            [2.0 if idx == 0 else 1.0 for idx in range(len(engaged_sorted))],
        )
        combined = combine(text_vec, centroid)
        profile_vec = np.asarray(combined, dtype=np.float32) if combined is not None else None

        ctx = RuleContext(
            tracks=profile.get("tracks", []),
            user_tech=profile.get("tech_tags", []),
            seniority_pref=profile.get("seniority_pref", []),
            location_pref=profile.get("location"),
        )
        per_persona.append(_evaluate_pool(candidates, embeddings, profile_vec, ctx, positives))

    return _aggregate(per_persona, seed), len(per_persona)


def build_profile_text_from(profile: dict) -> str:
    from app.ml.profile_embedding import build_profile_text

    return build_profile_text(
        tracks=profile.get("tracks"),
        tech_tags=profile.get("tech_tags"),
        seniority_pref=profile.get("seniority_pref"),
        location=profile.get("location"),
        headline=profile.get("headline"),
    )


# ── db mode ───────────────────────────────────────────────────────────────────

def sample_negatives(rng: random.Random, pool: list[int], engaged: set[int], n: int) -> list[int]:
    """n never-engaged job ids, deterministic under rng."""
    eligible = sorted(set(pool) - engaged)
    if len(eligible) <= n:
        return eligible
    return rng.sample(eligible, n)


def eval_db(seed: int) -> tuple[dict | None, int]:
    from sqlalchemy import select

    from app.db import get_session
    from app.models import Application, Job, Profile, User

    session = get_session()
    try:
        user_ids = [
            uid
            for (uid, n) in session.execute(
                select(Application.user_id, Application.job_id)
                .group_by(Application.user_id)
                .with_only_columns(Application.user_id, __import__("sqlalchemy").func.count())
            ).all()
            if n >= MIN_ENGAGEMENTS
        ]
        if not user_ids:
            return None, 0

        active_rows = session.execute(
            select(Job.id, Job.embedding).where(Job.is_active == True, Job.embedding.isnot(None))
        ).all()
        embeddings = {jid: np.asarray(list(vec), dtype=np.float32) for jid, vec in active_rows}
        job_rows = {
            j.id: j
            for j in session.execute(
                select(Job).where(Job.id.in_(list(embeddings.keys())))
            ).scalars()
        }

        per_user = []
        for uid in sorted(user_ids):
            rng = random.Random(seed + uid)
            engaged_ids = [
                jid
                for (jid,) in session.execute(
                    select(Application.job_id).where(Application.user_id == uid)
                ).all()
                if jid in embeddings
            ]
            if len(engaged_ids) < MIN_ENGAGEMENTS:
                continue
            engaged_ids.sort()
            n_holdout = max(1, round(len(engaged_ids) * HOLDOUT_FRACTION))
            holdout = set(rng.sample(engaged_ids, n_holdout))
            train = [i for i in engaged_ids if i not in holdout]

            negatives = sample_negatives(
                rng, list(embeddings.keys()), set(engaged_ids), NEGATIVE_RATIO * len(holdout)
            )
            candidate_ids = sorted(holdout | set(negatives))
            candidates = [job_rows[i] for i in candidate_ids]

            profile = session.get(Profile, uid)
            text = (
                build_profile_text_from(
                    {
                        "tracks": profile.tracks,
                        "tech_tags": profile.tech_tags,
                        "seniority_pref": profile.seniority_pref,
                        "location": profile.location,
                        "headline": profile.headline,
                    }
                )
                if profile
                else ""
            )
            text_vec = None
            if text:
                from app.ml.embedder import get_embedder

                text_vec = np.asarray(get_embedder().encode([text])[0], dtype=np.float32)
            centroid = weighted_centroid(
                [embeddings[i].tolist() for i in train], [1.0] * len(train)
            )
            combined = combine(text_vec, centroid)
            profile_vec = np.asarray(combined, dtype=np.float32) if combined is not None else None

            ctx = RuleContext(
                tracks=(profile.tracks or []) if profile else [],
                user_tech=(profile.tech_tags or []) if profile else [],
                seniority_pref=(profile.seniority_pref or []) if profile else [],
                remote_pref=profile.remote_pref.value if profile and profile.remote_pref else "any",
                location_pref=profile.location if profile else None,
                needs_sponsorship=(profile.needs_sponsorship or False) if profile else False,
                salary_floor=profile.salary_floor if profile else None,
            )
            per_user.append(_evaluate_pool(candidates, embeddings, profile_vec, ctx, holdout))

        if not per_user:
            return None, 0
        return _aggregate(per_user, seed), len(per_user)
    finally:
        session.close()


# ── report ────────────────────────────────────────────────────────────────────

def render_markdown(sections: list[tuple[str, dict, int]], seed: int) -> str:
    lines = [
        "# Matching Eval Results",
        "",
        f"Generated by `python -m scripts.eval_matching --seed {seed}` on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.",
        "",
        f"Metrics: recall@{RECALL_K}, NDCG@{NDCG_K}, MRR — higher is better; each cell is "
        "the mean with a bootstrap 95% CI in brackets. "
        "Rankers: **rule** = deterministic weighted scorer (production baseline), "
        "**semantic** = cosine against the profile vector "
        "(profile text + engaged-jobs centroid), **hybrid** = "
        "0.6·cosine + 0.4·normalized rule score (the For-You v2 production path).",
        "",
    ]
    for title, results, n in sections:
        lines += [f"## {title} (n={n})", ""]
        metric_names = list(next(iter(results.values())).keys())
        lines.append("| ranker | " + " | ".join(metric_names) + " |")
        lines.append("|" + "---|" * (len(metric_names) + 1))
        for ranker in ("rule", "semantic", "hybrid"):
            cells = []
            for m in metric_names:
                mean, lo, hi = results[ranker][m]
                cells.append(f"{mean:.3f} [{lo:.3f}–{hi:.3f}]")
            lines.append(f"| {ranker} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mode", choices=["personas", "db", "both"], default="both")
    parser.add_argument("--output", type=Path, default=None, help="markdown output path")
    args = parser.parse_args()

    sections: list[tuple[str, dict, int]] = []
    if args.mode in ("personas", "both"):
        results, n = eval_personas(args.seed)
        sections.append(("Synthetic personas", results, n))
    if args.mode in ("db", "both"):
        results, n = eval_db(args.seed)
        if results is None:
            print(f"db mode skipped: no users with >= {MIN_ENGAGEMENTS} engagements")
        else:
            sections.append(("Real users (held-out engagements)", results, n))

    report = render_markdown(sections, args.seed)
    print(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n")
        print(f"written to {args.output}")


if __name__ == "__main__":
    main()
