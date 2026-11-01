"""tools/neon_usage.py with mocked Neon API responses (the real API is never called)."""
import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("neon_usage", ROOT / "tools" / "neon_usage.py")
neon_usage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(neon_usage)

GB = 10 ** 9
GIB = 1024 ** 3


def fake_api(egress_bytes=0, compute_s=0, branch_sizes=(0,)):
    """Shapes follow Neon's GET /projects/{id} and GET /projects/{id}/branches."""
    def get(path):
        if path.endswith("/branches"):
            return {"branches": [{"id": f"br-{i}", "logical_size": s} for i, s in enumerate(branch_sizes)]}
        return {"project": {
            "id": "holy-resonance-91021279", "data_transfer_bytes": egress_bytes,
            "compute_time_seconds": compute_s, "active_time_seconds": compute_s * 3,
            "consumption_period_start": "2026-10-01T00:00:00Z",
            "consumption_period_end": "2026-11-01T00:00:00Z",
        }}
    return get


def run(get, **env):
    lines = []
    base = {"NEON_API_KEY": "k"}
    code = neon_usage.run(env={**base, **env}, get=get, out=lines.append)
    return code, "\n".join(lines)


def test_under_threshold_exits_zero():
    code, out = run(fake_api(1 * GB, 20 * 3600, (300 * 10**6,)))
    assert code == 0 and "under 60%" in out


def test_egress_over_60_percent_fails_with_a_clear_message():
    code, out = run(fake_api(3.5 * GB, 10 * 3600, (100 * 10**6,)))  # 70% of 5 GB
    assert code == 1
    assert "NEON USAGE ALERT" in out and "data transfer (egress) at 70%" in out


def test_compute_over_60_percent_fails():
    code, out = run(fake_api(0, 61 * 3600))
    assert code == 1 and "compute at 61%" in out


def test_storage_sums_branches_and_fails_over_60_percent():
    code, out = run(fake_api(0, 0, (400 * 10**6, 500 * 10**6)))  # 900 MB of 1 GiB
    assert code == 1 and "storage" in out


def test_exactly_60_percent_is_not_an_alert():
    code, _ = run(fake_api(3 * GB, 0))
    assert code == 0


def test_threshold_and_limits_are_configurable():
    code, _ = run(fake_api(1 * GB), NEON_ALERT_PCT="10")
    assert code == 1
    code, _ = run(fake_api(3.5 * GB), NEON_LIMIT_EGRESS_GB="10")
    assert code == 0


def test_missing_key_is_a_clear_nonzero_error_and_never_calls_the_api():
    lines = []

    def boom(path):
        raise AssertionError("must not call the API without a key")

    code = neon_usage.run(env={}, get=boom, out=lines.append)
    assert code == 2 and "NEON_API_KEY is not set" in lines[0]


def test_api_failure_is_reported_not_swallowed():
    def down(path):
        raise neon_usage.NeonApiError("Neon API /projects/x returned HTTP 401")

    lines = []
    code = neon_usage.run(env={"NEON_API_KEY": "k"}, get=down, out=lines.append)
    assert code == 2 and "HTTP 401" in lines[0]


def test_every_configured_project_is_checked():
    seen = []

    def get(path):
        seen.append(path)
        return fake_api()(path)

    run(get, NEON_PROJECT_IDS="p1, p2")
    assert [p for p in seen if p.endswith("/branches")] == ["/projects/p1/branches", "/projects/p2/branches"]


def test_only_get_requests_are_ever_built(monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return b"{}"

    def fake_urlopen(req, timeout=None):
        captured["method"], captured["auth"], captured["data"] = req.get_method(), req.get_header("Authorization"), req.data
        return _Resp()

    monkeypatch.setattr(neon_usage.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(neon_usage.json, "load", lambda r: {})
    neon_usage.api_get("/projects/x", "secret-key", base="https://example.invalid/api/v2")
    assert captured == {"method": "GET", "auth": "Bearer secret-key", "data": None}


def test_weekly_workflow_noops_without_the_secret():
    doc = yaml.safe_load((ROOT / ".github" / "workflows" / "neon-usage.yml").read_text())
    on = doc.get(True, doc.get("on"))
    assert len(on["schedule"]) == 1 and on["schedule"][0]["cron"].split()[4] != "*"  # weekly
    run_step = doc["jobs"]["usage"]["steps"][-1]
    assert run_step["env"]["NEON_API_KEY"] == "${{ secrets.NEON_API_KEY }}"
    script = run_step["run"]
    assert 'if [ -z "$NEON_API_KEY" ]' in script and "::notice::" in script and "exit 0" in script
    assert "tools/neon_usage.py" in script
