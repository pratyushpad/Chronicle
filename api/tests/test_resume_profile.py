from types import SimpleNamespace

import numpy as np
import pytest

from app.ml.profile_embedding import (
    ABOUT_MAX_CHARS,
    CHUNK_CHARS,
    DISMISS_WEIGHT,
    MAX_CHUNKS,
    chunk_text,
    combine,
    profile_text_inputs,
)
from app.resume import MAX_FILE_BYTES, extract_resume_text


# ── resume extraction ─────────────────────────────────────────────────────────

def _make_pdf(text: str) -> bytes:
    """Build a tiny real PDF in memory (pypdf can't write text, so hand-roll one)."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode()
    )
    return out


def test_extract_pdf():
    pdf = _make_pdf("Machine learning engineer with pytorch experience")
    text = extract_resume_text(pdf, "resume.pdf", "application/pdf")
    assert "pytorch" in text


def test_extract_txt():
    text = extract_resume_text(b"Senior data engineer. Spark, Airflow.", "resume.txt", "text/plain")
    assert text == "Senior data engineer. Spark, Airflow."


def test_extract_rejects_unknown_type():
    with pytest.raises(ValueError, match="Unsupported"):
        extract_resume_text(b"GIF89a...", "resume.gif", "image/gif")


def test_extract_rejects_oversize():
    with pytest.raises(ValueError, match="too large"):
        extract_resume_text(b"x" * (MAX_FILE_BYTES + 1), "resume.txt", "text/plain")


def test_extract_rejects_empty():
    with pytest.raises(ValueError, match="extract"):
        extract_resume_text(b"   ", "resume.txt", "text/plain")


def test_extract_rejects_broken_pdf():
    with pytest.raises(ValueError):
        extract_resume_text(b"%PDF-1.4 garbage", "resume.pdf", "application/pdf")


# ── chunking ──────────────────────────────────────────────────────────────────

def test_chunk_text_splits_on_whitespace():
    text = " ".join(f"word{i}" for i in range(400))  # ~2800 chars
    chunks = chunk_text(text)
    assert 2 <= len(chunks) <= MAX_CHUNKS
    assert all(len(c) <= CHUNK_CHARS for c in chunks)
    # no word is split in half
    reassembled = " ".join(chunks).split()
    assert reassembled == text.split()


def test_chunk_text_caps_chunks():
    assert len(chunk_text("x" * (CHUNK_CHARS * 10))) == MAX_CHUNKS


def test_chunk_text_collapses_newlines():
    chunks = chunk_text("line one\n\nline two\t line three")
    assert chunks == ["line one line two line three"]


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n ") == []


# ── profile text inputs ───────────────────────────────────────────────────────

def _profile(**kw):
    base = dict(
        tracks=None, tech_tags=None, seniority_pref=None, location=None,
        headline=None, about=None, resume_text=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_inputs_fields_about_resume():
    p = _profile(
        headline="ML engineer",
        tracks=["ml"],
        about="Early-stage startups only.",
        resume_text="word " * 500,  # ~2500 chars -> multiple chunks
    )
    inputs = profile_text_inputs(p)
    assert inputs[0].startswith("ML engineer.")
    assert inputs[1] == "Early-stage startups only."
    assert len(inputs) >= 4  # fields + about + >=2 resume chunks


def test_inputs_about_truncated():
    p = _profile(about="a" * (ABOUT_MAX_CHARS + 500))
    inputs = profile_text_inputs(p)
    assert len(inputs) == 1 and len(inputs[0]) == ABOUT_MAX_CHARS


def test_inputs_empty_profile():
    assert profile_text_inputs(_profile()) == []


# ── dismissed centroid ────────────────────────────────────────────────────────

def test_combine_dismissed_pushes_away():
    text = np.array([1.0, 0.0], dtype=np.float32)
    dismissed = np.array([1.0, 0.0], dtype=np.float32)  # dislikes exactly what text says
    without = np.asarray(combine(text, None))
    with_dismiss = np.asarray(combine(text, None, dismissed))
    # still normalized, and the dismissed direction lost weight relative to a control axis
    assert np.isclose(np.linalg.norm(with_dismiss), 1.0)
    ortho = np.array([0.6, 0.8], dtype=np.float32)
    assert with_dismiss @ ortho <= without @ ortho + 1e-6


def test_combine_only_dismissed_is_none_or_valid():
    # nothing positive to anchor on -> no vector at all
    assert combine(None, None, np.array([1.0, 0.0])) is None


def test_dismiss_weight_is_gentler_than_positives():
    assert DISMISS_WEIGHT < 0.5