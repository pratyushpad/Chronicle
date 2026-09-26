"""The alert digest must build for jobs that carry pay — after PR 1's backfill about half
of all rows do. A local variable named `html` once shadowed the html module inside
_build_email and turned every paid job into an UnboundLocalError (which rolled back the
whole alert run)."""
from types import SimpleNamespace

from app.ingest.alerts import _build_email


def _job(**kw):
    base = dict(id=1, title="Software Engineer Intern", location_normalized="austin, tx", remote=False,
                apply_url="https://example.com/apply", pay_min=45, pay_max=55, pay_currency="USD",
                pay_period="hour")
    base.update(kw)
    return SimpleNamespace(**base)


def test_digest_builds_and_shows_pay_as_posted():
    user = SimpleNamespace(email="a@example.com")
    search = SimpleNamespace(name="interns")
    subject, body = _build_email(user, search, [(_job(), "Acme"), (_job(id=2, pay_period=None, pay_min=None, pay_max=None), "Beta")])
    assert "2 new roles" in subject
    assert "$45 to 55/hr" in body
    assert "$45k" not in body  # never the old annualized "$Xk" rendering


def test_posting_and_user_text_is_escaped():
    """Titles, company names, places and search names are free text from postings and
    users; an apply URL is linked only when it's http(s)."""
    user = SimpleNamespace(email="a@example.com")
    search = SimpleNamespace(name='<img src=x onerror=alert(1)>\nBcc: x@evil.test')
    evil = _job(title="<script>alert(1)</script>", location_normalized="<b>nyc</b>",
                apply_url="javascript:alert(1)")
    subject, body = _build_email(user, search, [(evil, "Acme' onmouseover='x")])
    assert "\n" not in subject and "Bcc: x@evil.test" in subject  # one header line
    assert "<script>" not in body and "&lt;script&gt;" in body
    assert "<img" not in body and "<b>nyc" not in body
    assert "javascript:" not in body
    assert "Acme&#x27; onmouseover=&#x27;x" in body


def test_email_needs_all_three_settings(monkeypatch):
    from app.ingest import alerts

    for key, value in (("RESEND_API_KEY", "k"), ("RESEND_FROM", "Chronicle <a@b.test>"), ("APP_URL", "https://c.test")):
        monkeypatch.setattr(alerts, key, value)
    assert alerts.email_configured()
    for key in ("RESEND_API_KEY", "RESEND_FROM", "APP_URL"):
        monkeypatch.setattr(alerts, key, "")
        assert not alerts.email_configured()
        monkeypatch.setattr(alerts, key, "x")
