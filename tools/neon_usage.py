#!/usr/bin/env python3
"""Neon free-tier usage check. Read-only: it only issues GET requests.

    NEON_API_KEY=... python tools/neon_usage.py

Reads the current billing period's data transfer (egress), compute time and storage for each
project and exits 1 with a plain message when any of them is past NEON_ALERT_PCT (default 60)
percent of the free limit, 2 when it could not check (no key, API error), 0 otherwise.

Neon API (https://api-docs.neon.tech/reference/getproject, .../listprojectbranches):
  GET /api/v2/projects/{project_id}            -> project.data_transfer_bytes,
        project.compute_time_seconds, project.consumption_period_start/end (current period)
  GET /api/v2/projects/{project_id}/branches   -> branches[].logical_size (bytes)

Compute is reported in CU-seconds (compute units x seconds), so hours = seconds / 3600.
Storage is the sum of branch logical sizes, a conservative proxy: Neon bills a child branch at
the smaller of its own changes and its logical size, so this can over-report, never under.

Config (env): NEON_PROJECT_IDS (comma list, default Folio-Dev holy-resonance-91021279),
NEON_ALERT_PCT, NEON_LIMIT_EGRESS_GB (5), NEON_LIMIT_COMPUTE_CU_HOURS (100),
NEON_LIMIT_STORAGE_GB (1; the free plan's per-project storage), NEON_API_BASE.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_PROJECTS = "holy-resonance-91021279"
GB = 1024 ** 3
# Neon's pricing page counts egress in GB; treat 1 GB as 10^9 bytes for the transfer cap,
# which makes the check slightly stricter than a GiB reading.
GB_DECIMAL = 10 ** 9


class NeonApiError(Exception):
    pass


@dataclass
class Metric:
    project: str
    name: str
    used: float
    limit: float
    unit: str

    @property
    def pct(self) -> float:
        return 100.0 * self.used / self.limit if self.limit else 0.0

    def line(self, threshold: float) -> str:
        flag = "OVER" if self.pct > threshold else "ok  "
        return f"{flag} {self.project} {self.name}: {self.used:.2f} / {self.limit:g} {self.unit} ({self.pct:.1f}%)"


def api_get(path: str, key: str, base: str | None = None) -> dict:
    """One authenticated GET. Never sends a body or any other method."""
    base = (base or os.environ.get("NEON_API_BASE") or "https://console.neon.tech/api/v2").rstrip("/")
    req = urllib.request.Request(
        base + path, method="GET",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed https base
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise NeonApiError(f"Neon API {path} returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise NeonApiError(f"Neon API {path} failed: {type(exc).__name__}") from None


def collect(project_id: str, get, limits: dict) -> list[Metric]:
    """Metrics for one project. `get(path) -> dict` is injectable so tests never hit the network."""
    project = get(f"/projects/{project_id}").get("project") or {}
    branches = get(f"/projects/{project_id}/branches").get("branches") or []
    egress = float(project.get("data_transfer_bytes") or 0)
    compute_s = float(project.get("compute_time_seconds") or 0)
    storage = float(sum((b.get("logical_size") or 0) for b in branches))
    return [
        Metric(project_id, "data transfer (egress)", egress / GB_DECIMAL, limits["egress_gb"], "GB"),
        Metric(project_id, "compute", compute_s / 3600.0, limits["compute_cu_hours"], "CU-hours"),
        Metric(project_id, "storage", storage / GB, limits["storage_gb"], "GiB"),
    ]


def limits_from_env(env=None) -> dict:
    env = os.environ if env is None else env
    return {
        "egress_gb": float(env.get("NEON_LIMIT_EGRESS_GB", "5")),
        "compute_cu_hours": float(env.get("NEON_LIMIT_COMPUTE_CU_HOURS", "100")),
        "storage_gb": float(env.get("NEON_LIMIT_STORAGE_GB", "1")),
    }


def run(env=None, get=None, out=print) -> int:
    env = os.environ if env is None else env
    key = env.get("NEON_API_KEY", "")
    if not key:
        out("NEON_API_KEY is not set; cannot check Neon usage.")
        return 2
    threshold = float(env.get("NEON_ALERT_PCT", "60"))
    projects = [p.strip() for p in env.get("NEON_PROJECT_IDS", DEFAULT_PROJECTS).split(",") if p.strip()]
    get = get or (lambda path: api_get(path, key))
    limits = limits_from_env(env)
    metrics: list[Metric] = []
    try:
        for pid in projects:
            metrics += collect(pid, get, limits)
    except NeonApiError as exc:
        out(f"Could not read Neon usage: {exc}")
        return 2
    for m in metrics:
        out(m.line(threshold))
    over = [m for m in metrics if m.pct > threshold]
    if over:
        names = "; ".join(f"{m.project} {m.name} at {m.pct:.0f}%" for m in over)
        out(f"NEON USAGE ALERT: past {threshold:g}% of the free limit: {names}. "
            f"Cut traffic or ingest frequency before the cap suspends the database.")
        return 1
    out(f"Neon usage is under {threshold:g}% of every free limit.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
