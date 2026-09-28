"""
Email alert worker — runs after each ingest.
For each active saved_search with alert_frequency != off, finds new jobs
matching the stored query_json, creates Notification rows, and sends
email digests via Resend.
"""
import asyncio
import html
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models import Company, Job, Notification, SavedSearch, User
from app.db import get_session
from .pay import format_pay

log = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
# Display name is Chronicle; the sending address stays on the Resend-verified
# folioapp.dev domain until a Chronicle domain is verified there.
# `or`, not a getenv default: an unset GitHub secret arrives as an empty string, and an
# empty sender would make Resend reject every alert email.
RESEND_FROM = os.getenv("RESEND_FROM") or "Chronicle <alerts@folioapp.dev>"
APP_URL = (os.getenv("APP_URL") or "http://localhost:3001").rstrip("/")


def email_configured() -> bool:
    """Email digests go out only when RESEND_API_KEY is set on the host that runs ingest
    (RESEND_FROM and APP_URL fall back to defaults above). Until then the site doesn't
    promise email (/meta says so)."""
    return bool(RESEND_API_KEY and RESEND_FROM and APP_URL)


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _safe_url(url: str | None) -> str | None:
    """Only http(s) links go into an email; everything is attribute-escaped."""
    u = (url or "").strip()
    return _esc(u) if u.lower().startswith(("https://", "http://")) else None


# Only what the digest reads: never the 20 KB description or the embedding. Every row
# since the oldest due cutoff is loaded, so this keeps the pass small on Render's 512 MB.
_ALERT_COLUMNS = (
    Job.id, Job.title, Job.department, Job.remote, Job.experience_level,
    Job.location_normalized, Job.apply_url, Job.first_seen_at,
    Job.pay_min, Job.pay_max, Job.pay_currency, Job.pay_period,
)


def _matches_query(job: Job, company_name: str, query: dict) -> bool:
    if q := query.get("q"):
        if q.lower() not in job.title.lower():
            return False
    if company := query.get("company"):
        if company.lower() not in company_name.lower():
            return False
    if dept := query.get("department"):
        # Exact match, like the feed filter (a substring made "IT" match "Quality").
        if not job.department or dept.strip().lower() != job.department.lower():
            return False
    if query.get("remote") is not None:
        if job.remote != query["remote"]:
            return False
    if exp := query.get("experience_level"):
        if not job.experience_level or exp.lower() not in job.experience_level.lower():
            return False
    return True


def _build_email(user: User, search: SavedSearch, jobs: list[tuple[Job, str]]) -> tuple[str, str]:
    # A header can't carry a line break (header injection); names are free text.
    name = " ".join(str(search.name).split())[:80]
    subject = f"Chronicle: {len(jobs)} new role{'s' if len(jobs) != 1 else ''} matching \"{name}\""
    rows = ""
    for job, company_name in jobs[:20]:
        # Pay as posted ("$45 to 55/hr") — salary_min/max are annualized sort keys, and
        # rendering them as "$Xk" is exactly the hourly-intern bug the pay_* columns fix.
        pay_label = format_pay(job.pay_min, job.pay_max, job.pay_currency, job.pay_period)
        salary = ""
        if pay_label:
            salary = f"<span style='color:#6b6b6b;font-size:12px;margin-left:8px'>{html.escape(pay_label)}</span>"
        # Every value from a posting or a user is escaped: titles and search names are
        # free text, and an apply URL is only linked when it's http(s).
        place = f" · {_esc(job.location_normalized)}" if job.location_normalized else ""
        apply_url = _safe_url(job.apply_url)
        apply_cell = (
            f"<a href='{apply_url}' style='font-family:system-ui,sans-serif;font-size:12px;color:#b8860b;text-decoration:none'>Apply →</a>"
            if apply_url else ""
        )
        rows += f"""
        <tr>
          <td style='padding:12px 0;border-bottom:1px solid #e8e4df'>
            <a href='{_esc(APP_URL)}/jobs/{int(job.id)}' style='font-family:Georgia,serif;font-size:16px;color:#1a1a1a;text-decoration:none;font-weight:600'>
              {_esc(job.title)}
            </a>{salary}<br>
            <span style='font-family:system-ui,sans-serif;font-size:13px;color:#6b6b6b'>
              {_esc(company_name)}{place}{" · Remote" if job.remote else ""}
            </span>
          </td>
          <td style='padding:12px 0;border-bottom:1px solid #e8e4df;text-align:right;vertical-align:top'>
            {apply_cell}
          </td>
        </tr>"""

    # Not named `html`: that would shadow the html module used for escaping above and
    # raise UnboundLocalError for any job with pay.
    body = f"""
    <div style='max-width:560px;margin:0 auto;font-family:system-ui,sans-serif;background:#fafaf8;padding:32px 24px'>
      <p style='font-family:Georgia,serif;font-size:28px;color:#1a1a1a;margin:0 0 4px'>Chronicle</p>
      <p style='font-size:13px;color:#b8860b;letter-spacing:0.1em;text-transform:uppercase;margin:0 0 32px'>JOB ALERT · {_esc(name)}</p>
      <p style='font-size:15px;color:#6b6b6b;margin:0 0 24px'>
        {len(jobs)} new role{'s' if len(jobs) != 1 else ''} since your last alert:
      </p>
      <table width='100%' cellpadding='0' cellspacing='0' style='border-top:1px solid #e8e4df'>
        {rows}
      </table>
      <p style='margin-top:32px'>
        <a href='{_esc(APP_URL)}/jobs' style='background:#b8860b;color:#fff;padding:12px 24px;border-radius:6px;font-size:14px;text-decoration:none;font-family:system-ui,sans-serif'>
          View all roles →
        </a>
      </p>
      <p style='font-size:11px;color:#b0a898;margin-top:32px'>
        You're receiving this because you saved a search on Chronicle.
        <a href='{_esc(APP_URL)}/saved' style='color:#b0a898'>Manage alerts</a>
      </p>
    </div>"""
    return subject, body


async def _send_email(to: str, subject: str, html: str) -> bool:
    if not email_configured():
        log.info("RESEND_API_KEY not set; skipping an alert email")  # never log addresses
        return False
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": RESEND_FROM, "to": [to], "subject": subject, "html": html},
        )
        if not resp.is_success:
            log.error("Resend error %d: %s", resp.status_code, resp.text[:200])
            return False
    return True


async def run_alerts(session: Session, run_start: datetime) -> None:
    now = datetime.now(timezone.utc)

    # Honor the chosen cadence (slightly under the nominal period so a run that lands
    # a few minutes early doesn't silently push every digest a full day/week out).
    min_gap = {"daily": timedelta(hours=20), "weekly": timedelta(days=6)}

    def _due(s: SavedSearch) -> bool:
        gap = min_gap.get(s.alert_frequency)
        return not (gap and s.last_alerted_at and now - s.last_alerted_at < gap)

    searches = [
        s
        for s in session.execute(
            select(SavedSearch).where(SavedSearch.alert_frequency != "off")
        ).scalars()
        if _due(s)
    ]
    if not searches:
        return

    # Candidate pool: everything first seen since the oldest due cutoff, so a weekly
    # digest includes the whole week's matches — not just this run's. run_start caps
    # the fallback for searches that have never alerted.
    pool_since = min(
        (s.last_alerted_at or max(s.created_at, run_start - timedelta(days=7)) for s in searches),
        default=run_start,
    )
    new_job_rows = session.execute(
        select(*_ALERT_COLUMNS, Company.name.label("company_name"))
        .join(Company, Job.company_id == Company.id)
        .where(Job.is_active == True, Job.first_seen_at >= pool_since)
    ).all()

    for search in searches:
        cutoff = search.last_alerted_at or search.created_at
        user = session.get(User, search.user_id)
        if not user:
            continue

        matched = [
            (row, row.company_name)
            for row in new_job_rows
            if row.first_seen_at >= cutoff and _matches_query(row, row.company_name, search.query_json)
        ]

        if not matched:
            continue

        # Write in-app notification
        notif = Notification(
            user_id=user.id,
            type="new_jobs_alert",
            payload={
                "search_name": search.name,
                "job_count": len(matched),
                "search_id": search.id,
                "sample_titles": [j.title for j, _ in matched[:3]],
            },
            read=False,
            created_at=now,
        )
        session.add(notif)

        # Send email digest
        subject, body = _build_email(user, search, matched)
        sent = await _send_email(user.email, subject, body)
        if sent:
            log.info("Alert email sent: %d jobs for saved search %d", len(matched), search.id)

        search.last_alerted_at = now

    session.commit()
