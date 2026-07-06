from app.ml.text import DESCRIPTION_CHARS, build_embedding_text


def test_full_template():
    text = build_embedding_text(
        title="Senior ML Engineer",
        company_name="Stripe",
        department="Engineering",
        location="San Francisco, CA",
        tech_tags=["python", "pytorch"],
        description_text="Build models.",
    )
    assert text == (
        "Senior ML Engineer at Stripe. Engineering. San Francisco, CA. "
        "Tags: python, pytorch. Build models."
    )


def test_all_optional_fields_missing():
    assert build_embedding_text("Engineer", None, None, None, None, None) == "Engineer."


def test_empty_tags_omitted():
    text = build_embedding_text("Engineer", "Acme", None, None, [], None)
    assert text == "Engineer at Acme."
    assert "Tags" not in text


def test_description_truncated():
    desc = "x" * (DESCRIPTION_CHARS + 500)
    text = build_embedding_text("Engineer", None, None, None, None, desc)
    assert len(text) == len("Engineer. ") + DESCRIPTION_CHARS


def test_no_html_expected():
    # The template trusts its input is already stripped; a stray tag passes
    # through verbatim, which is why callers must use normalize.strip_html.
    text = build_embedding_text("Engineer", None, None, None, None, "<b>hi</b>")
    assert "<b>" in text
