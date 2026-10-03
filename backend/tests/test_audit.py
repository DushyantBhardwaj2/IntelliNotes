"""Security regression tests from the post-hardening backend audit.

Covers: filename/path-traversal spoofing, upload DoS caps, telemetry
privacy, secret redaction in agent traces, and auth coverage of every
mutating or data-bearing endpoint.
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.security import redact_secrets

client = TestClient(app)


# ---------------------------------------------------------------------------
# Filename spoofing / path traversal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    [
        "../../etc/passwd.pdf",
        "..\\..\\windows\\system32\\evil.pdf",
        "notes.pdf.exe",
        "no-extension",
        ".hidden.pdf",
        "..pdf",
    ],
)
def test_upload_rejects_spoofed_filenames(bad_name):
    response = client.post(
        "/upload-document/",
        files={"file": (bad_name, b"%PDF-fake", "application/pdf")},
    )
    assert response.status_code == 400
    assert "Only PDF files are supported" in response.json()["detail"]


def test_load_pdf_chunks_sanitizes_filename_metadata():
    from app.ingestion.loader import load_pdf_chunks

    page = MagicMock()
    page.extract_text.return_value = "Clean document text with enough words to chunk."
    reader = MagicMock()
    reader.pages = [page]
    with patch("app.ingestion.loader.PdfReader", return_value=reader):
        chunks = load_pdf_chunks(b"fake", filename="..\\..\\etc\\hostile.pdf")
    assert all("/" not in c.metadata["filename"] for c in chunks)
    assert all("\\" not in c.metadata["filename"] for c in chunks)
    assert chunks[0].metadata["filename"] == "hostile.pdf"


# ---------------------------------------------------------------------------
# Upload DoS caps
# ---------------------------------------------------------------------------


def _reader_with_pages(count, text="Some repeated document content here."):
    pages = []
    for _ in range(count):
        page = MagicMock()
        page.extract_text.return_value = text
        pages.append(page)
    reader = MagicMock()
    reader.pages = pages
    return reader


def test_oversized_pdf_is_rejected_with_400():
    from app.ingestion.loader import MAX_PDF_FILE_MB, extract_pdf_pages

    huge = b"x" * (MAX_PDF_FILE_MB * 1024 * 1024 + 1)
    with pytest.raises(ValueError):
        extract_pdf_pages(huge)


def test_excessive_page_count_is_rejected():
    from app.ingestion.loader import MAX_PDF_PAGES, extract_pdf_pages

    with patch(
        "app.ingestion.loader.PdfReader", return_value=_reader_with_pages(MAX_PDF_PAGES + 1)
    ):
        with pytest.raises(ValueError, match="limit"):
            extract_pdf_pages(b"fake")


def test_zip_bomb_page_text_is_rejected():
    from app.ingestion.loader import MAX_PAGE_TEXT_CHARS, extract_pdf_pages

    reader = _reader_with_pages(1, text="A" * (MAX_PAGE_TEXT_CHARS + 1))
    with patch("app.ingestion.loader.PdfReader", return_value=reader):
        with pytest.raises(ValueError, match="too much text"):
            extract_pdf_pages(b"fake")


# ---------------------------------------------------------------------------
# Chroma telemetry privacy
# ---------------------------------------------------------------------------


def test_telemetry_env_forced_off():
    from app.ingestion.vectorstore import _telemetry_off

    for var in ("ANONYMIZED_TELEMETRY", "ALLOW_CHROMA_TELEMETRY_RECORDING"):
        import os

        saved = os.environ.get(var)
        try:
            os.environ.pop(var, None)
            _telemetry_off()
            assert os.environ[var] == "False"
        finally:
            if saved is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = saved


# ---------------------------------------------------------------------------
# Secret redaction in agent traces
# ---------------------------------------------------------------------------


def test_redact_google_api_key():
    payload = {"trace": [{"detail": "auth failed for key AIzaSyA1234567890abcdefghijklmnopqrstu"}]}
    out = redact_secrets(payload)
    assert "AIzaSy" not in str(out)
    assert "[REDACTED]" in str(out)


def test_redact_tavily_key():
    out = redact_secrets("tvly-abcdefghijklmnop")
    assert "tvly-" not in out


def test_redact_database_url_credentials():
    out = redact_secrets("connect failed: postgresql://admin:hunter2@db.example.com:5432/n")
    assert "hunter2" not in out
    assert "db.example.com" in out  # host preserved for debuggability


def test_redact_key_value_assignments():
    out = redact_secrets("error near api_key = 'supersecretvalue123'")
    assert "supersecretvalue123" not in out
    assert "api_key" in out.lower()


def test_redact_preserves_ordinary_content():
    text = "Quota exceeded: 429 for model gemini-3.5-flash-lite, retry after 60s."
    assert redact_secrets(text) == text


def test_redact_secrets_recurses_through_trace_structures():
    payload = {
        "reason": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c",
        "sources": [{"note": "token: abcdefgh1234"}],
        "count": 3,
        "flag": True,
    }
    out = redact_secrets(payload)
    assert "eyJ" not in out["reason"]
    assert "abcdefgh1234" not in out["sources"][0]["note"]
    assert out["count"] == 3 and out["flag"] is True


def test_chat_trace_is_redacted_in_response():
    with patch("app.main.get_graph") as mock_get_graph:
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "answer": "ok",
            "trace": [{"step": "grade", "reason": "key AIzaSyA1234567890abcdefghijklmnopqrstu quota"}],
        }
        mock_get_graph.return_value = mock_graph
        response = client.post("/chat/", json={"message": "hi"})
    assert response.status_code == 200
    assert "AIzaSy" not in response.text
    assert "[REDACTED]" in response.text


# ---------------------------------------------------------------------------
# Auth coverage: every mutating/data-bearing endpoint requires the key
# ---------------------------------------------------------------------------


def test_documents_endpoint_requires_key_when_auth_enabled():
    with patch.object(settings, "api_key", "secret-key"):
        assert client.get("/documents").status_code == 401
        assert client.get("/documents", headers={"X-API-Key": "secret-key"}).status_code == 200


def test_delete_single_document_requires_key_when_auth_enabled():
    with (
        patch.object(settings, "api_key", "secret-key"),
        patch("app.main.vectorstore.delete_document", return_value=1),
    ):
        assert client.delete("/documents/whatever").status_code == 401
        ok = client.delete("/documents/whatever", headers={"X-API-Key": "secret-key"})
        assert ok.status_code == 200
