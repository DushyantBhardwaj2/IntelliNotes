import pytest
from unittest.mock import MagicMock, patch

from app.ingestion.loader import (
    Chunk,
    clean_text,
    chunk_text,
    extract_pdf_pages,
    extract_pdf_text,
    load_pdf_chunks,
)


def test_clean_text():
    raw = "Hello\x00 world!   This   is   a   test.\n\n\n\nNew paragraph."
    cleaned = clean_text(raw)
    assert "\x00" not in cleaned
    assert "   " not in cleaned
    assert "\n\n\n\n" not in cleaned
    assert cleaned == "Hello world! This is a test.\n\nNew paragraph."


def test_chunk_text_basic():
    text = "Word " * 100
    chunks = chunk_text(text, chunk_size=50, chunk_overlap=10)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 65  # word boundary threshold
        assert len(c.split()) >= 5


def test_chunk_text_short():
    text = "Too short"
    chunks = chunk_text(text)
    # Less than 5 words should be filtered out
    assert chunks == []


@patch("app.ingestion.loader.PdfReader")
def test_extract_pdf_pages(mock_reader_cls):
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Page one content with sufficient length words."
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Page two content also contains words."

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page1, mock_page2]
    mock_reader_cls.return_value = mock_reader

    pages = extract_pdf_pages(b"fake_pdf_bytes")
    assert len(pages) == 2
    assert pages[0][0] == 1
    assert "Page one" in pages[0][1]
    assert pages[1][0] == 2
    assert "Page two" in pages[1][1]


@patch("app.ingestion.loader.PdfReader")
def test_load_pdf_chunks_success(mock_reader_cls):
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "IntelliNotes agentic RAG system architecture page one text."
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Page two details about vector retrieval, grader sufficiency, and grounding."

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page1, mock_page2]
    mock_reader_cls.return_value = mock_reader

    chunks = load_pdf_chunks(b"fake_pdf_bytes", filename="notes.pdf", doc_id="doc-123")
    assert len(chunks) >= 2
    for i, chunk in enumerate(chunks):
        assert isinstance(chunk, Chunk)
        assert chunk.metadata["doc_id"] == "doc-123"
        assert chunk.metadata["filename"] == "notes.pdf"
        assert chunk.metadata["chunk_index"] == i
        assert "page_number" in chunk.metadata
        assert chunk.metadata["total_chunks"] == len(chunks)


@patch("app.ingestion.loader.PdfReader")
def test_load_pdf_chunks_empty_raises_error(mock_reader_cls):
    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]
    mock_reader_cls.return_value = mock_reader

    with pytest.raises(ValueError, match="No extractable text found in this PDF"):
        load_pdf_chunks(b"fake_empty_pdf", filename="empty.pdf")


@patch("app.ingestion.loader.PdfReader")
def test_load_pdf_chunks_too_sparse_raises_error(mock_reader_cls):
    """Text long enough to pass MIN_TEXT_LENGTH but too sparse to chunk
    (fewer than 5 words) must raise a clean ValueError, not return []."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Supercalifragilisticexpialidocious"

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]
    mock_reader_cls.return_value = mock_reader

    with pytest.raises(ValueError, match="too short or sparse"):
        load_pdf_chunks(b"fake_sparse_pdf", filename="sparse.pdf")
