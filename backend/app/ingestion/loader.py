from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass, field

from pypdf import PdfReader

from app.config import settings

MIN_TEXT_LENGTH = 30


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_pages(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Extract clean text for each page of the PDF as (page_number, text).
    
    Page numbers are 1-indexed.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    extracted = []
    for idx, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        cleaned = clean_text(raw_text)
        if cleaned:
            extracted.append((idx, cleaned))
    return extracted


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Convenience helper extracting all text joined together."""
    pages = extract_pdf_pages(pdf_bytes)
    return "\n\n".join(text for _, text in pages)


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[str]:
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap

    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        if current and current_len + len(word) + 1 > size:
            chunks.append(" ".join(current))
            kept: list[str] = []
            kept_len = 0
            for existing in reversed(current):
                if kept_len + len(existing) + 1 > overlap:
                    break
                kept.insert(0, existing)
                kept_len += len(existing) + 1
            current = kept
            current_len = kept_len
        current.append(word)
        current_len += len(word) + 1

    if current:
        chunks.append(" ".join(current))
    return [chunk for chunk in chunks if len(chunk.split()) >= 5]


def load_pdf_chunks(
    pdf_bytes: bytes,
    filename: str,
    doc_id: str | None = None,
) -> list[Chunk]:
    """Parse PDF bytes into page-tagged chunks with rich metadata."""
    doc_id = doc_id or uuid.uuid4().hex
    pages = extract_pdf_pages(pdf_bytes)

    total_chars = sum(len(text) for _, text in pages)
    if total_chars < MIN_TEXT_LENGTH:
        raise ValueError(
            "No extractable text found in this PDF. "
            "It may be empty or contain only scanned images."
        )

    all_chunks: list[Chunk] = []
    for page_num, page_text in pages:
        page_pieces = chunk_text(page_text)
        for piece in page_pieces:
            all_chunks.append(
                Chunk(
                    text=piece,
                    metadata={
                        "doc_id": doc_id,
                        "filename": filename,
                        "page_number": page_num,
                    },
                )
            )

    # If individual pages had very short pieces (< 5 words), fallback to full text
    if not all_chunks:
        full_text = "\n\n".join(text for _, text in pages)
        pieces = chunk_text(full_text)
        all_chunks = [
            Chunk(
                text=piece,
                metadata={
                    "doc_id": doc_id,
                    "filename": filename,
                    "page_number": 1,
                },
            )
            for piece in pieces
        ]

    # Text long enough to pass MIN_TEXT_LENGTH can still be too sparse to
    # produce a single usable chunk (e.g. a few very long "words").
    if not all_chunks:
        raise ValueError(
            "No usable text chunks could be extracted from this PDF. "
            "The extracted text is too short or sparse to index."
        )

    # Assign global chunk indices and total chunks
    total = len(all_chunks)
    for i, chunk in enumerate(all_chunks):
        chunk.metadata["chunk_index"] = i
        chunk.metadata["total_chunks"] = total

    return all_chunks

