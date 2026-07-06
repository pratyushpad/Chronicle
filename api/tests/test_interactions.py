import pytest
from pydantic import ValidationError

from app.schemas import InteractionBatchIn, InteractionIn


def test_valid_batch():
    batch = InteractionBatchIn(
        events=[
            {"job_id": 1, "event": "impression", "surface": "search"},
            {"job_id": 2, "event": "click", "surface": "feed"},
            {"job_id": 3, "event": "save", "surface": "feed"},
        ]
    )
    assert len(batch.events) == 3


def test_batch_size_cap():
    events = [{"job_id": i, "event": "impression", "surface": "search"} for i in range(101)]
    with pytest.raises(ValidationError):
        InteractionBatchIn(events=events)
    assert len(InteractionBatchIn(events=events[:100]).events) == 100


def test_invalid_event_rejected():
    with pytest.raises(ValidationError):
        InteractionIn(job_id=1, event="hover", surface="search")


def test_invalid_surface_rejected():
    with pytest.raises(ValidationError):
        InteractionIn(job_id=1, event="click", surface="email")
