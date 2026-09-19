"""PDF processing utilities using PyMuPDF (fitz)."""

from __future__ import annotations

import io
from typing import Any
import pymupdf
from PIL import Image


class PDFDocument:
    """Wrapper around PyMuPDF Document for extraction and rendering."""

    def __init__(self, file_bytes: bytes, filename: str = "document.pdf") -> None:
        self.filename = filename
        self.doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        self.page_count: int = len(self.doc)

    def get_page_text(self, page_index: int) -> str:
        """Extract text from a specific page (0-indexed)."""
        if 0 <= page_index < self.page_count:
            page = self.doc[page_index]
            return page.get_text()
        return ""

    def get_all_pages_text(self) -> list[dict[str, Any]]:
        """Extract text from all pages with page metadata (1-indexed for display)."""
        pages_data = []
        for i in range(self.page_count):
            page_text = self.get_page_text(i)
            pages_data.append({
                "page": i + 1,
                "text": page_text,
                "char_count": len(page_text),
                "line_count": len(page_text.splitlines()),
            })
        return pages_data

    def render_page_image(self, page_index: int, dpi: int = 150) -> Image.Image:
        """Render a PDF page to a PIL Image."""
        if 0 <= page_index < self.page_count:
            page = self.doc[page_index]
            pix = page.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")
            return Image.open(io.BytesIO(img_bytes))
        raise IndexError(f"Page {page_index} out of bounds (0..{self.page_count - 1})")

    def close(self) -> None:
        """Close document handle."""
        if self.doc:
            self.doc.close()
