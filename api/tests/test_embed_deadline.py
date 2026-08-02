"""embed_missing_jobs must stop at the deadline and never load ONNX needlessly."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.ml import embed_jobs


def test_deadline_in_past_embeds_nothing(monkeypatch):
    def _fail():
        raise AssertionError("embedder must not load when deadline already passed")

    monkeypatch.setattr(embed_jobs, "get_embedder", _fail)
    session = MagicMock()

    total = embed_jobs.embed_missing_jobs(
        session, deadline=datetime.now(tz=timezone.utc) - timedelta(seconds=1)
    )

    assert total == 0
    session.execute.assert_not_called()


def test_no_pending_rows_skips_model_load(monkeypatch):
    def _fail():
        raise AssertionError("embedder must not load when nothing is pending")

    monkeypatch.setattr(embed_jobs, "get_embedder", _fail)
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    total = embed_jobs.embed_missing_jobs(session)

    assert total == 0


def test_deadline_stops_between_pages(monkeypatch):
    """A multi-page backlog must stop at the deadline after finishing a page,
    not run every remaining page to exhaustion."""
    from types import SimpleNamespace

    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    deadline = base + timedelta(seconds=10)
    ticks = iter([base, base + timedelta(seconds=20)])  # page 1 in budget, page 2 not

    class FakeDatetime:
        @staticmethod
        def now(tz=None):
            return next(ticks)

    monkeypatch.setattr(embed_jobs, "datetime", FakeDatetime)
    monkeypatch.setattr(embed_jobs, "build_embedding_text", lambda **kw: "text")

    encode_calls = []

    class FakeEmbedder:
        def encode(self, texts, batch_size):
            encode_calls.append(len(texts))
            return [[0.0] * 3 for _ in texts]

    monkeypatch.setattr(embed_jobs, "get_embedder", FakeEmbedder)

    row = SimpleNamespace(
        id=1, title="SWE", department=None, location_normalized=None,
        location_raw=None, tech_tags=None, description_text="x", company_name="Acme",
    )
    select_result = MagicMock()
    select_result.all.return_value = [row, row]
    session = MagicMock()
    session.execute.side_effect = [select_result, MagicMock()]  # page select, then update

    total = embed_jobs.embed_missing_jobs(session, deadline=deadline)

    assert total == 2
    assert encode_calls == [2]  # exactly one page embedded
    assert session.execute.call_count == 2  # no second page select after the deadline
