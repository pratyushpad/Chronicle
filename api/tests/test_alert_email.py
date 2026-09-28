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


def test_empty_email_settings_fall_back_to_defaults(monkeypatch):
    """An unset GitHub secret arrives as an empty string; the sender must not be empty."""
    import importlib

    import app.ingest.alerts as alerts

    monkeypatch.setenv("RESEND_FROM", "")
    monkeypatch.setenv("APP_URL", "")
    reloaded = importlib.reload(alerts)
    try:
        assert reloaded.RESEND_FROM == "Chronicle <alerts@folioapp.dev>"
        assert reloaded.APP_URL == "http://localhost:3001"
    finally:
        monkeypatch.delenv("RESEND_FROM")
        monkeypatch.delenv("APP_URL")
        importlib.reload(alerts)
