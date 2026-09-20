"""Document ingestion with native text and local Ollama OCR routes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, TypedDict

from src.pdf_processor import PDFDocument


class IngestPage(TypedDict):
    """One numbered page of normalized document text.

    Attributes:
        page: One-based source page number.
        text: Native or OCR-produced text for that page.
    """

    page: int
    text: str


class IngestResult(TypedDict):
    """Normalized ingest payload passed into extraction and reconciliation.

    Attributes:
        route: ``native`` for direct text or ``ollama`` for an OCR route.
        pdf_type: Source classification such as ``text`` or ``text_based``.
        text: Concatenated page text.
        pages: Numbered per-page text records.
    """

    route: Literal["native", "ollama"]
    pdf_type: str
    text: str
    pages: list[IngestPage]


def ingest_document(
    source: str | os.PathLike[str] | bytes,
    *,
    filename: str | None = None,
    force_ocr: bool = False,
) -> IngestResult:
    """Ingest one text or PDF document without any Agnes call.

    Args:
        source: File path or uploaded bytes.
        filename: Original upload name required when ``source`` is bytes.
        force_ocr: Route PDFs through OCR even when native text is available.

    Returns:
        Native or OCR-routed text with document type and per-page records.

    Raises:
        ValueError: If the source extension is not ``.txt`` or ``.pdf``.
        OSError: If a local source cannot be read.
        RuntimeError: If PDF processing cannot complete.
    """
    source_name = filename or (Path(source).name if not isinstance(source, bytes) else "")
    suffix = Path(source_name).suffix.lower()

    if suffix == ".txt":
        if isinstance(source, bytes):
            text = source.decode("utf-8", errors="replace")
        else:
            text = Path(source).read_text(encoding="utf-8", errors="replace")
        return {
            "route": "native",
            "pdf_type": "text",
            "text": text,
            "pages": [{"page": 1, "text": text}],
        }

    if suffix != ".pdf":
        raise ValueError("Only .txt and .pdf documents are supported.")

    with PDFDocument(source, filename=source_name, force_ocr=force_ocr) as document:
        pages = [
            {"page": int(page["page"]), "text": str(page["text"])}
            for page in document.get_all_pages_text()
        ]
        return {
            "route": "native" if document.skipped_ollama else "ollama",
            "pdf_type": document.pdf_type,
            "text": "\n\n".join(page["text"] for page in pages),
            "pages": pages,
        }
