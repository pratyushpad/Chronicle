"""
Email alert worker — runs after each ingest.
For each active saved_search with alert_frequency != off, finds new jobs
matching the stored query_json, creates Notification rows, and sends
email digests via Resend.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models import Company, Job, Notification, SavedSearch, User
from app.db import get_session

log = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "Folio <alerts@folioapp.dev>")
APP_URL = os.getenv("APP_URL", "http://localhost:3001")


def _matches_query(job: Job, company_name: str, query: dict) -> bool:
    if q := query.get("q"):
        if q.lower() not in job.title.lower():
            return False
    if company := query.get("company"):
        if company.lower() not in company_name.lower():
            return False
    if dept := query.get("department"):
        if not job.department or dept.lower() not in job.department.lower():
            return False
    if query.get("remote") is not None:
        if job.remote != query["remote"]:
            return False
    if exp := query.get("experience_level"):
        if not job.experience_level or exp.lower() not in job.experience_level.lower():
            return False
    return True


def _build_email(user: User, search: SavedSearch, jobs: list[tuple[Job, str]]) -> tuple[str, str]:
    subject = f"Chronicle: {len(jobs)} new role{'s' if len(jobs) != 1 else ''} matching \"{search.name}\""
    rows = ""
    for job, company_name in jobs[:20]:
        salary = ""
        if job.salary_min:
            lo = f"${job.salary_min // 1000}k"
            hi = f"–${job.salary_max // 1000}k" if job.salary_max else ""
            salary = f"<span style='color:#6b6b6b;font-size:12px;margin-left:8px'>{lo}{hi}</span>"
        rows += f"""
        <tr>
          <td style='padding:12px 0;border-bottom:1px solid #e8e4df'>
            <a href='{APP_URL}/jobs/{job.id}' style='font-family:Georgia,serif;font-size:16px;color:#1a1a1a;text-decoration:none;font-weight:600'>
              {job.title}
            </a>{salary}<br>
            <span style='font-family:system-ui,sans-serif;font-size:13px;color:#6b6b6b'>
              {company_name}{f" · {job.location_normalized}" if job.location_normalized else ""}{" · Remote" if job.remote else ""}
            </span>
          </td>
          <td style='padding:12px 0;border-bottom:1px solid #e8e4df;text-align:right;vertical-align:top'>
            <a href='{job.apply_url}' style='font-family:system-ui,sans-serif;font-size:12px;color:#b8860b;text-decoration:none'>Apply →</a>
          </td>
        </tr>"""

    html = f"""
    <div style='max-width:560px;margin:0 auto;font-family:system-ui,sans-serif;background:#fafaf8;padding:32px 24px'>
      <p style='font-family:Georgia,serif;font-size:28px;color:#1a1a1a;margin:0 0 4px'>Folio</p>
      <p style='font-size:13px;color:#b8860b;letter-spacing:0.1em;text-transform:uppercase;margin:0 0 32px'>JOB ALERT · {search.name}</p>
      <p style='font-size:15px;color:#6b6b6b;margin:0 0 24px'>
        {len(jobs)} new role{'s' if len(jobs) != 1 else ''} since your last alert:
      </p>
      <table width='100%' cellpadding='0' cellspacing='0' style='border-top:1px solid #e8e4df'>
        {rows}
      </table>
      <p style='margin-top:32px'>
        <a href='{APP_URL}/jobs' style='background:#b8860b;color:#fff;padding:12px 24px;border-radius:6px;font-size:14px;text-decoration:none;font-family:system-ui,sans-serif'>
          View all roles →
        </a>
      </p>
      <p style='font-size:11px;color:#b0a898;margin-top:32px'>
        You're receiving this because you saved a search on Folio.
        <a href='{APP_URL}/saved' style='color:#b0a898'>Manage alerts</a>
      </p>
    </div>"""
    return subject, html


async def _send_email(to: str, subject: str, html: str) -> bool:
    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY not set — skipping email to %s", to)
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
    searches = session.execute(
        select(SavedSearch).where(SavedSearch.alert_frequency != "off")
    ).scalars().all()

    if not searches:
        return

    # Load all new jobs from this ingest run
    new_job_rows = session.execute(
        select(Job, Company.name.label("company_name"))
        .join(Company, Job.company_id == Company.id)
        .where(Job.is_active == True, Job.first_seen_at >= run_start)
    ).all()

    now = datetime.now(timezone.utc)

    for search in searches:
        cutoff = search.last_alerted_at or search.created_at
        user = session.get(User, search.user_id)
        if not user:
            continue

        matched = [
            (row.Job, row.company_name)
            for row in new_job_rows
            if row.Job.first_seen_at >= cutoff and _matches_query(row.Job, row.company_name, search.query_json)
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
        subject, html = _build_email(user, search, matched)
        sent = await _send_email(user.email, subject, html)
        if sent:
            log.info("Alert email sent to %s: %d jobs for search '%s'", user.email, len(matched), search.name)

        search.last_alerted_at = now

    session.commit()
