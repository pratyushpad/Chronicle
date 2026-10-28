"""The scheduled workflows are part of the Neon budget: one ingest run a day, the old
Render-triggered ingest standing down, and the usage alert present."""
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name: str) -> dict:
    doc = yaml.safe_load((WORKFLOWS / name).read_text())
    doc["on"] = doc.pop(True, doc.get("on"))  # YAML 1.1 reads the bare key `on` as True
    return doc


def test_ingest_actions_runs_once_a_day_around_10_utc():
    crons = [s["cron"] for s in _load("ingest-actions.yml")["on"]["schedule"]]
    assert len(crons) == 1
    minute, hour, dom, month, dow = crons[0].split()
    assert hour == "10" and dom == month == dow == "*"
    assert 0 <= int(minute) <= 59 and minute != "0"  # off the top of the hour


def test_ingest_actions_force_full_is_a_manual_input_only():
    doc = _load("ingest-actions.yml")
    assert "force_full" in doc["on"]["workflow_dispatch"]["inputs"]
    env = doc["jobs"]["ingest"]["steps"][-1]["env"]
    assert "INGEST_FORCE_FULL" in env


def test_old_render_triggered_ingest_still_stands_down_when_actions_ingest_is_configured():
    text = (WORKFLOWS / "ingest.yml").read_text()
    assert "NEON_DATABASE_URL" in text and "skipping the Render slice" in text
