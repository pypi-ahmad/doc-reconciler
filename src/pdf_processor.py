"""Windows-native PDF routing through pdf-inspector and optional Ollama OCR."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Self

import pdf_inspector
import pypdfium2 as pdfium
from PIL import Image

from src.ollama_client import (
    DEFAULT_OLLAMA_MODEL,
    extract_tables_with_ollama,
    is_ollama_available,
)


@dataclass
class PageData:
    """Describe one native or OCR-routed document page.

    Attributes:
        page: One-based page number.
        text: Extracted native or OCR text.
        source: Extraction engine used for this page.
        char_count: Number of text characters.
        line_count: Number of text lines.
        image_path: Saved PNG path when rendering was required.
        needs_ocr: Whether OCR was requested for the page.
        ocr_reason: Classification reason for OCR routing.
    """

    page: int
    text: str
    source: str
    char_count: int
    line_count: int
    image_path: str | None = None
    needs_ocr: bool = False
    ocr_reason: str = ""


def build_ocr_prompt(include_tables: bool = True) -> str:
    """Build the required PaddleOCR-VL instruction prefixes.

    Args:
        include_tables: Include the table-recognition instruction when true.

    Returns:
        Prompt beginning with ``OCR:`` and, optionally, ``Table Recognition:``.
    """
    prompt = "OCR:\nExtract all visible text from this invoice page as Markdown."
    if include_tables:
        prompt += "\n\nTable Recognition:\nPreserve rows, columns, numbers, and reading order."
    return prompt


class PDFDocument:
    """Classify a PDF locally, then route eligible pages through Ollama OCR.

    Use this class as a context manager so byte-backed temporary PDFs and the
    underlying PDFium document are closed. Native text-based PDFs avoid Ollama
    unless ``force_ocr`` is true.

    Attributes:
        pdf_type: ``pdf-inspector`` classification result.
        confidence: Classification confidence reported by ``pdf-inspector``.
        page_count: Number of source pages.
        pages_data: Extracted page records.
        warnings: Safe routing and OCR fallback messages.
        skipped_ollama: Whether native text satisfied the request.
    """

    def __init__(
        self,
        file_source: str | os.PathLike[str] | bytes,
        filename: str = "document.pdf",
        pages_dir: str = "data/pages",
        ollama_model: str | None = None,
        include_tables: bool = True,
        force_ocr: bool = False,
    ) -> None:
        self.filename = filename
        self.pages_dir = pages_dir
        self.ollama_model = ollama_model or os.environ.get("OLLAMA_OCR_MODEL", DEFAULT_OLLAMA_MODEL)
        self.include_tables = include_tables
        self.force_ocr = force_ocr
        self.warnings: list[str] = []
        self._temp_file: str | None = None
        Path(self.pages_dir).mkdir(parents=True, exist_ok=True)

        if isinstance(file_source, bytes):
            descriptor, path = tempfile.mkstemp(prefix="doc_reconciler_", suffix=".pdf")
            with os.fdopen(descriptor, "wb") as temp_file:
                temp_file.write(file_source)
            self.path = path
            self._temp_file = path
        else:
            self.path = os.fspath(file_source)

        self.inspect_result = pdf_inspector.process_pdf(self.path)
        self.pdf_type = str(self.inspect_result.pdf_type)
        self.confidence = float(self.inspect_result.confidence)
        self.raw_markdown = str(self.inspect_result.markdown or "")
        self._pdfium_doc = pdfium.PdfDocument(self.path)
        self.page_count = int(self.inspect_result.page_count)
        if self.page_count != len(self._pdfium_doc):
            self.page_count = len(self._pdfium_doc)

        extracted = pdf_inspector.extract_pages_markdown(self.path)
        native_pages = list(extracted.pages)
        if not self.force_ocr and self.pdf_type == "text_based" and self.raw_markdown.strip():
            self.extraction_engine = "pdf-inspector"
            self.skipped_ollama = True
            self.pages_data = [
                self._native_page(index, native_pages) for index in range(self.page_count)
            ]
        else:
            self.extraction_engine = "pdf-inspector + Ollama OCR"
            self.skipped_ollama = False
            self.pages_data = self._route_image_pages(native_pages)

    def _native_page(self, index: int, native_pages: list[object]) -> dict[str, object]:
        page = native_pages[index] if index < len(native_pages) else None
        text = str(getattr(page, "markdown", "") or "").strip()
        if not text and self.page_count == 1:
            text = self.raw_markdown.strip()
        data = PageData(
            page=index + 1,
            text=text,
            source="pdf-inspector (native)",
            char_count=len(text),
            line_count=len(text.splitlines()),
            needs_ocr=bool(getattr(page, "needs_ocr", False)),
            ocr_reason=str(getattr(page, "ocr_reason", "") or ""),
        )
        return asdict(data)

    def _route_image_pages(self, native_pages: list[object]) -> list[dict[str, object]]:
        available, status = is_ollama_available(model=self.ollama_model)
        if not available:
            self.warnings.append(
                f"Ollama OCR unavailable: {status}. Using native text when available; "
                "upload a fixture .txt when scanned pages have no text."
            )

        pages: list[dict[str, object]] = []
        for index in range(self.page_count):
            page = native_pages[index] if index < len(native_pages) else None
            native_text = str(getattr(page, "markdown", "") or "").strip()
            needs_ocr = self.force_ocr or bool(getattr(page, "needs_ocr", False)) or not native_text
            needs_ocr = needs_ocr or self.pdf_type in {"scanned", "image_based"}
            reason = str(getattr(page, "ocr_reason", "") or f"PDF type: {self.pdf_type}")

            if not needs_ocr:
                pages.append(self._native_page(index, native_pages))
                continue

            image_path = os.path.join(self.pages_dir, f"page_{index + 1}.png")
            self.save_page_image(index, image_path)
            text = native_text
            source = "pdf-inspector (native fallback)"
            if available:
                try:
                    text = extract_tables_with_ollama(
                        image_path=image_path,
                        prompt=build_ocr_prompt(self.include_tables),
                        model=self.ollama_model,
                    )
                    source = f"Ollama ({self.ollama_model})"
                except RuntimeError as error:
                    self.warnings.append(
                        f"Ollama OCR failed on page {index + 1}: {error}. Using native text."
                    )
            if not text:
                text = "[No native text available. Upload a text fixture or start Ollama OCR.]"
            pages.append(
                asdict(
                    PageData(
                        page=index + 1,
                        text=text,
                        source=source,
                        char_count=len(text),
                        line_count=len(text.splitlines()),
                        image_path=image_path,
                        needs_ocr=True,
                        ocr_reason=reason,
                    )
                )
            )
        return pages

    def render_page_image(self, page_index: int, scale: float = 2.0) -> Image.Image:
        """Render one zero-based page through pypdfium2.

        Args:
            page_index: Zero-based PDF page index.
            scale: PDFium render scale.

        Returns:
            Rendered PIL image.

        Raises:
            IndexError: If ``page_index`` is outside the document.
        """
        if not 0 <= page_index < len(self._pdfium_doc):
            raise IndexError(f"Page index {page_index} is outside this document.")
        return self._pdfium_doc[page_index].render(scale=scale).to_pil()

    def save_page_image(self, page_index: int, output_path: str, scale: float = 2.0) -> str:
        """Render and save one zero-based PDF page as a PNG.

        Args:
            page_index: Zero-based PDF page index.
            output_path: Target PNG path.
            scale: PDFium render scale.

        Returns:
            The output path after saving the image.

        Raises:
            IndexError: If ``page_index`` is outside the document.
        """
        image = self.render_page_image(page_index, scale=scale)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, "PNG")
        return output_path

    def get_page_text(self, page_index: int) -> str:
        """Return extracted text for one zero-based page, or an empty string.

        Args:
            page_index: Zero-based page index.

        Returns:
            Stored page text when available; otherwise an empty string.
        """
        return (
            str(self.pages_data[page_index]["text"])
            if 0 <= page_index < len(self.pages_data)
            else ""
        )

    def get_all_pages_text(self) -> list[dict[str, object]]:
        """Return the ordered extracted page records.

        Returns:
            Native and OCR page records generated during construction.
        """
        return self.pages_data

    def close(self) -> None:
        """Close PDFium resources and delete a temporary byte-backed PDF."""
        self._pdfium_doc.close()
        if self._temp_file:
            try:
                os.remove(self._temp_file)
            except FileNotFoundError:
                pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def inspect_and_process_pdf(
    path: str,
    pages_dir: str = "data/pages",
    ollama_model: str | None = None,
) -> PDFDocument:
    """Create a PDF processor through the compatibility helper.

    Args:
        path: Local PDF path.
        pages_dir: Directory for rendered OCR page images.
        ollama_model: Optional OCR model override.

    Returns:
        Open ``PDFDocument`` instance. Call ``close`` or use a context manager.
    """
    return PDFDocument(path, Path(path).name, pages_dir, ollama_model)
