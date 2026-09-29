"""The ONNX model must not stay resident in the web process after an ingest run.

On Render's 512 MB free tier the embedder is ~150-250 MB of RSS. Loaded lazily during
a run's embed phase and never released, it left so little headroom that the box OOM'd
while completely idle. run_ingest now releases it as its last act.

Nothing here loads real ONNX — Embedder is always stubbed.
"""
import threading

import pytest

from app.ml import embedder as embedder_mod


class _FakeEmbedder:
    """Stand-in for the real Embedder; counts how often the model 'loads'."""

    loads = 0

    def __init__(self):
        type(self).loads += 1

    def encode(self, texts, batch_size=16):
        return [[0.0] * 3 for _ in texts]


@pytest.fixture
def stub_model(monkeypatch):
    """Swap in a fake model and guarantee the module global is clean either side."""
    _FakeEmbedder.loads = 0
    monkeypatch.setattr(embedder_mod, "Embedder", _FakeEmbedder)
    monkeypatch.setattr(embedder_mod, "_instance", None, raising=False)
    yield _FakeEmbedder
    monkeypatch.setattr(embedder_mod, "_instance", None, raising=False)


def test_release_clears_the_global_and_forces_a_reload(stub_model):
    first = embedder_mod.get_embedder()
    assert embedder_mod._instance is first
    assert stub_model.loads == 1

    assert embedder_mod.release_embedder() is True
    assert embedder_mod._instance is None

    second = embedder_mod.get_embedder()
    assert second is not first
    assert stub_model.loads == 2  # the reload really happened


def test_get_embedder_is_a_singleton_between_releases(stub_model):
    assert embedder_mod.get_embedder() is embedder_mod.get_embedder()
    assert stub_model.loads == 1


def test_release_with_nothing_loaded_is_a_no_op(stub_model):
    assert embedder_mod._instance is None

    assert embedder_mod.release_embedder() is False
    assert stub_model.loads == 0


def test_double_release_is_a_no_op(stub_model):
    embedder_mod.get_embedder()

    assert embedder_mod.release_embedder() is True
    assert embedder_mod.release_embedder() is False
    assert embedder_mod._instance is None


def test_release_does_not_break_an_in_flight_encode(stub_model):
    """A search thread holding its own reference must finish against the model it
    already has — tearing the session out mid-encode would be a crash, not a saving."""
    held = embedder_mod.get_embedder()

    embedder_mod.release_embedder()

    assert held.encode(["still works"]) == [[0.0, 0.0, 0.0]]


def test_a_concurrent_release_cannot_interleave_with_a_load(monkeypatch):
    """FastAPI serves sync endpoints from a threadpool, so a search request can call
    get_embedder() at the same moment the ingest task calls release_embedder(). The
    shared lock must make the releaser wait out the load instead of cutting into it.
    """
    monkeypatch.setattr(embedder_mod, "_instance", None, raising=False)
    load_started = threading.Event()
    releaser_blocked_during_load = []

    class _SlowEmbedder(_FakeEmbedder):
        def __init__(self):
            super().__init__()
            load_started.set()
            # A releaser that shares our lock is stuck here; an unguarded one would
            # have sailed through release_embedder() and exited well inside 200ms.
            releaser.join(timeout=0.2)
            releaser_blocked_during_load.append(releaser.is_alive())

    def _release():
        load_started.wait(timeout=2)
        embedder_mod.release_embedder()

    releaser = threading.Thread(target=_release)
    monkeypatch.setattr(embedder_mod, "Embedder", _SlowEmbedder)

    releaser.start()
    instance = embedder_mod.get_embedder()
    releaser.join(timeout=2)

    assert releaser_blocked_during_load == [True]  # release waited for the lock
    assert isinstance(instance, _SlowEmbedder)  # a fully built instance was returned
    assert releaser.is_alive() is False  # and the releaser got through afterwards


# ── ordering inside run_ingest ────────────────────────────────────────────────


def test_run_ingest_releases_the_embedder_last(drive_run_ingest, fake_company, monkeypatch):
    calls = []
    monkeypatch.setattr(
        embedder_mod, "release_embedder", lambda: calls.append("release") or True
    )

    async def _alerts(session, run_start):
        calls.append("alerts")

    drive_run_ingest([fake_company()], {}, alerts=_alerts)

    assert calls == ["alerts", "release"]  # release strictly after anything that embeds


def test_release_runs_even_when_alerts_raise(drive_run_ingest, fake_company, monkeypatch):
    """Alerts are best-effort; a failure there must not strand 200 MB in the process."""
    calls = []
    monkeypatch.setattr(
        embedder_mod, "release_embedder", lambda: calls.append("release") or True
    )

    async def _alerts(session, run_start):
        calls.append("alerts")
        raise RuntimeError("resend is down")

    drive_run_ingest([fake_company()], {}, alerts=_alerts)

    assert calls == ["alerts", "release"]


def test_a_failing_release_never_fails_the_run(drive_run_ingest, fake_company, monkeypatch):
    def _boom():
        raise RuntimeError("gc exploded")

    monkeypatch.setattr(embedder_mod, "release_embedder", _boom)

    run, _ = drive_run_ingest([fake_company()], {})

    assert run.finished_at is not None  # the run still completed and was written


def test_release_declines_while_an_encode_is_in_flight(stub_model, monkeypatch):
    """Release must NOT drop the global while an encode is running: the running
    encode pins its model, so a drop would let the next get_embedder() load a second
    model alongside it — transient double residency is the one state a 512 MB box
    cannot absorb. A busy release is skipped; a later one gets it."""
    embedder_mod.get_embedder()
    monkeypatch.setattr(embedder_mod, "_active_encodes", 1)

    assert embedder_mod.release_embedder() is False
    assert embedder_mod._instance is not None

    monkeypatch.setattr(embedder_mod, "_active_encodes", 0)
    assert embedder_mod.release_embedder() is True
    assert embedder_mod._instance is None


def test_encode_tracks_the_in_flight_counter(monkeypatch):
    """The guard only works if the real Embedder.encode maintains the counter —
    incremented for the duration of the encode, back to zero after, even on error."""
    inst = object.__new__(embedder_mod.Embedder)  # skip __init__ (no real ONNX)
    seen = {}

    def _fake_batches(texts, batch_size):
        seen["during"] = embedder_mod._active_encodes
        return []

    monkeypatch.setattr(inst, "_encode_batches", _fake_batches, raising=False)
    monkeypatch.setattr(embedder_mod, "_active_encodes", 0)

    inst.encode(["x"])
    assert seen["during"] == 1
    assert embedder_mod._active_encodes == 0

    def _boom(texts, batch_size):
        raise RuntimeError("mid-encode failure")

    monkeypatch.setattr(inst, "_encode_batches", _boom, raising=False)
    with pytest.raises(RuntimeError):
        inst.encode(["x"])
    assert embedder_mod._active_encodes == 0

