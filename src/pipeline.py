"""End-to-end document reconciliation pipeline."""

from __future__ import annotations

import os

from openai import OpenAI

from src.agnes_client import DEFAULT_AGNES_MODEL, get_agnes_client
from src.extract import extract_text
from src.ingest import IngestResult, ingest_document
from src.models import ReconcileState
from src.retry import retry_failed_checks


def reconcile_ingest(
    ingested: IngestResult,
    *,
    tolerance: float = 0.01,
    max_retries: int = 3,
    client: OpenAI | None = None,
    model: str = DEFAULT_AGNES_MODEL,
) -> ReconcileState:
    """Extract, check, and retry one existing ingest result.

    Args:
        ingested: Normalized text and pages returned by ``ingest_document``.
        tolerance: Maximum allowed absolute numeric delta.
        max_retries: Requested retry count; downstream logic caps it at three.
        client: Optional Agnes-compatible client for tests or custom callers.
        model: Agnes model identifier.

    Returns:
        Session-safe state with extracted values, Python checks, and retry log.

    Raises:
        ValueError: If extraction input or Agnes credentials are invalid.
    """
    active_client = client or get_agnes_client()
    extraction = extract_text(ingested["text"], client=active_client, model=model)
    state = ReconcileState(
        items=extraction.items,
        totals=extraction.totals,
        texts=[page["text"] for page in ingested["pages"]],
    )
    return retry_failed_checks(
        state,
        tolerance=tolerance,
        max_retries=max_retries,
        client=active_client,
        model=model,
    )


def reconcile_document(
    source: str | os.PathLike[str] | bytes,
    *,
    filename: str | None = None,
    force_ocr: bool = False,
    tolerance: float = 0.01,
    max_retries: int = 3,
    client: OpenAI | None = None,
    model: str = DEFAULT_AGNES_MODEL,
) -> ReconcileState:
    """Run ingest, extraction, checks, and the bounded retry loop.

    Args:
        source: Text/PDF path or uploaded document bytes.
        filename: Original name required for byte uploads.
        force_ocr: Force PDF OCR even when native text is available.
        tolerance: Maximum allowed absolute numeric delta.
        max_retries: Requested retry count; downstream logic caps it at three.
        client: Optional Agnes-compatible client for tests or custom callers.
        model: Agnes model identifier.

    Returns:
        Final reconciliation state, including any unresolved Python failures.

    Raises:
        ValueError: If ingest, extraction, or credentials are invalid.
        OSError: If a local source cannot be read.
    """
    ingested = ingest_document(source, filename=filename, force_ocr=force_ocr)
    return reconcile_ingest(
        ingested,
        tolerance=tolerance,
        max_retries=max_retries,
        client=client,
        model=model,
    )
