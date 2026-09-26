"""Summarize one GitHub Actions ingest run against Neon's free-tier compute budget.

  python tools/ingest_budget_report.py <report.json> >> "$GITHUB_STEP_SUMMARY"

Neon's free plan includes 100 compute-unit hours (CU-h) a month; running out suspends the
database. This is an ESTIMATE: it assumes the compute is awake for the run's wall-clock
time (the ingest plus the embedding sweep) plus Neon's 5-minute suspend delay, at NEON_CU:
set it to your compute endpoint's autoscale MAXIMUM (default 0.25, the free tier's
minimum, which undercounts if autoscaling goes higher). The real number is in the Neon
console (Billing → Compute).
"""
import json
import os
import sys

FREE_CU_HOURS = 100
SUSPEND_DELAY_S = 300


def main() -> None:
    report = json.load(open(sys.argv[1]))
    cu = float(os.environ.get("NEON_CU", "0.25"))
    runs_per_month = int(os.environ.get("RUNS_PER_MONTH", "60"))  # a 12-hour schedule
    print("## Ingest run")
    if "skipped" in report:
        print(f"Skipped: {report['skipped']}.")
        return
    if "crashed" in report:
        print(f"**Crashed:** {report['crashed']}. The run row was closed; see /status.")
        return
    secs = report.get("seconds_total") or report.get("seconds") or 0
    per_run = (secs + SUSPEND_DELAY_S) / 3600 * cu
    monthly = per_run * runs_per_month
    print(f"- Run {report['run_id']}: {secs} s including the embedding sweep, boards {report['boards_ok']}/{report['boards_total']} ok "
          f"({report['boards_failed']} failed), jobs seen {report['jobs_seen']}, new {report['jobs_new']}, "
          f"closed {report['jobs_closed']}")
    print(f"- Neon compute estimate at {cu} CU: {per_run:.3f} CU-h this run; "
          f"{monthly:.1f} CU-h/month at {runs_per_month} runs "
          f"({monthly / FREE_CU_HOURS:.0%} of the free {FREE_CU_HOURS} CU-h). "
          "Ingest is not the only load: the site's own queries use the same budget.")
    if monthly > FREE_CU_HOURS * 0.5:
        print(f"- **Warning:** this schedule alone would use over half of the free compute.")


if __name__ == "__main__":
    main()
