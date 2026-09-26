"""run_alerts against real Postgres (TEST_DATABASE_URL; skips without): the column-only
query still matches and writes the in-app notification, and no email is attempted
while email isn't configured. Hermetic: rolled back."""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest import alerts
from app.ingest.alerts import _ALERT_COLUMNS
from app.models import AlertFrequency, ATSSource, Company, Job, Notification, SavedSearch, User


def test_alert_run_notifies_without_loading_descriptions(pg_engine, monkeypatch):
    sent = []

    async def _fake_send(to, subject, body):
        sent.append(to)
        return False

    monkeypatch.setattr(alerts, "_send_email", _fake_send)
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            s = Session(bind=conn)
            s.commit = s.flush
            now = datetime.now(timezone.utc)
            co = Company(name="AlertCo", ats=ATSSource.greenhouse, slug="alert-co-test", active=True)
            user = User(auth_provider="google", auth_provider_id="alert-test", email="alert-test@example.com")
            s.add_all([co, user])
            s.flush()
            s.add(SavedSearch(user_id=user.id, name="robotics", query_json={"q": "robotics"},
                              alert_frequency=AlertFrequency.daily, created_at=now - timedelta(days=1)))
            s.add(Job(company_id=co.id, source=ATSSource.greenhouse, source_job_id="al-1",
                      title="Robotics Intern <b>", title_normalized="robotics intern", apply_url="https://e.test",
                      dedup_key="dk-al-1", first_seen_at=now, last_seen_at=now, is_active=True,
                      description_text="<p>" + "x" * 5000 + "</p>"))
            s.flush()
            asyncio.run(alerts.run_alerts(s, now - timedelta(hours=1)))
            notes = s.execute(select(Notification).where(Notification.user_id == user.id)).scalars().all()
            assert len(notes) == 1 and notes[0].payload["sample_titles"] == ["Robotics Intern <b>"]
            assert sent == ["alert-test@example.com"]  # attempted; _send_email itself gates on config
            loaded = {c.key for c in _ALERT_COLUMNS}
            assert "description_text" not in loaded and "embedding" not in loaded
        finally:
            outer.rollback()
