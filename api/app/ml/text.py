"""Embedding text template — the single source of what a job 'says' to the model."""

DESCRIPTION_CHARS = 1200


def build_embedding_text(
    title: str,
    company_name: str | None,
    department: str | None,
    location: str | None,
    tech_tags: list[str] | None,
    description_text: str | None,
) -> str:
    """Render the canonical embedding input for a job.

    description_text must already be HTML-stripped (normalize.strip_html).
    Keep this in sync with any stored embeddings — changing the template
    invalidates them.
    """
    parts = [f"{title} at {company_name}." if company_name else f"{title}."]
    if department:
        parts.append(f"{department}.")
    if location:
        parts.append(f"{location}.")
    if tech_tags:
        parts.append(f"Tags: {', '.join(tech_tags)}.")
    if description_text:
        parts.append(description_text[:DESCRIPTION_CHARS])
    return " ".join(parts)
