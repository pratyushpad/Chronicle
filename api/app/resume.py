"""Resume text extraction. We keep extracted text only — never the file."""
import io
import logging

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_TEXT_CHARS = 20_000


def extract_resume_text(data: bytes, filename: str, content_type: str | None) -> str:
    """Extract plain text from an uploaded resume (.pdf or .txt).

    Raises ValueError with a user-facing message on unsupported/broken input.
    """
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("File too large (max 2 MB)")
    name = (filename or "").lower()
    if name.endswith(".pdf") or content_type == "application/pdf":
        text = _extract_pdf(data)
    elif name.endswith(".txt") or (content_type or "").startswith("text/"):
        text = data.decode("utf-8", errors="ignore")
    else:
        raise ValueError("Unsupported file type — upload a PDF or plain-text file")
    text = text.strip()
    if not text:
        raise ValueError("Couldn't extract any text from that file")
    return text[:MAX_TEXT_CHARS]


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")  # try empty password; raises if truly locked
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ValueError:
        raise
    except Exception as exc:
        log.info("PDF extraction failed: %s", exc)
        raise ValueError("Couldn't read that PDF — try exporting it again or upload .txt") from exc
