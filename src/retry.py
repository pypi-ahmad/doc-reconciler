"""Bounded Agnes patch loop with deterministic Python verification."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from src.agnes_client import DEFAULT_AGNES_MODEL, create_chat_completion
from src.checks import run_checks
from src.extract import clean_json_text
from src.models import (
    DocumentTotal,
    DocumentTotals,
    LineItem,
    ReconcileState,
    ReconciliationResult,
    RetryLogEntry,
)

DEFAULT_CACHE_PATH = Path("data/cache/last_reconcile.json")
RAW_LOG_LIMIT = 160


class ItemPatch(BaseModel):
    """Represent a supported correction to one active-pipeline line item.

    Attributes:
        row_index: Zero-based item index to update.
        sku: Replacement SKU when supported by source evidence.
        desc: Replacement description when supported by source evidence.
        qty: Replacement quantity when supported by source evidence.
        unit_price: Replacement unit price when supported by source evidence.
        amount: Replacement amount when supported by source evidence.
    """

    row_index: int
    sku: str | None = None
    desc: str | None = None
    qty: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class TotalsPatch(BaseModel):
    """Represent supported corrections to active-pipeline stated totals.

    Attributes:
        subtotal: Replacement stated subtotal.
        tax: Replacement stated tax.
        total: Replacement stated grand total.
        page: Replacement source page.
    """

    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    page: int | None = None


class ReconcilePatch(BaseModel):
    """Represent the narrow JSON patch returned by an Agnes retry request.

    Attributes:
        items: Optional supported row corrections.
        totals: Optional supported stated-total corrections.
    """

    items: list[ItemPatch] | None = None
    totals: TotalsPatch | None = None


def _document_total(totals: DocumentTotals) -> DocumentTotal:
    return DocumentTotal(
        subtotal=totals.subtotal,
        tax=totals.tax,
        total=totals.total,
        page=totals.page,
    )


def _sum_message(items: list[LineItem], totals: DocumentTotals) -> str:
    calculated = sum(
        (Decimal(str(item.amount)) for item in items if item.amount is not None),
        Decimal(0),
    )
    stated = Decimal(str(totals.total)) if totals.total is not None else Decimal(0)
    delta = calculated - stated
    return f"sum(items)={calculated:.2f} stated_total={stated:.2f} delta={delta:+.2f}"


def _truncate_raw(row: dict[str, Any]) -> dict[str, Any]:
    logged = dict(row)
    raw = str(logged.get("raw") or "")
    logged["raw"] = raw if len(raw) <= RAW_LOG_LIMIT else f"{raw[: RAW_LOG_LIMIT - 3]}..."
    return logged


def _request_patch(
    client: OpenAI,
    model: str,
    rows: list[dict[str, Any]],
    totals: DocumentTotals,
    sum_message: str,
) -> ReconcilePatch:
    system_prompt = """Review only the supplied failing extracted rows and stated totals.
Return one JSON patch with this exact shape:
{
  "items": [
    {"row_index": 0, "sku": null, "desc": null, "qty": null, "unit_price": null, "amount": null}
  ],
  "totals": {"subtotal": null, "tax": null, "total": null, "page": null}
}
Omit items or totals when no extraction correction is supported by the supplied evidence.
Never change a stated value merely to force arithmetic to pass. Never declare the checks resolved.
Python will merge the patch and independently rerun every check. Return JSON only."""
    user_prompt = (
        f"Python discrepancy: {sum_message}\n\n"
        f"Failing rows only:\n{json.dumps(rows, indent=2)}\n\n"
        f"Stated totals:\n{totals.model_dump_json(indent=2)}"
    )
    response = create_chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        client=client,
        model=model,
    )
    try:
        return ReconcilePatch.model_validate_json(
            clean_json_text(response.choices[0].message.content or "")
        )
    except ValidationError as error:
        raise ValueError(f"Agnes retry patch failed schema validation: {error}") from error


def _merge_patch(state: ReconcileState, patch: ReconcilePatch) -> None:
    for correction in patch.items or []:
        if not 0 <= correction.row_index < len(state.items):
            continue
        item = state.items[correction.row_index]
        for field in ("sku", "desc", "qty", "unit_price", "amount"):
            value = getattr(correction, field)
            if value is not None:
                setattr(item, field, value)
        if correction.desc is not None:
            item.description = correction.desc
    if patch.totals is not None:
        for field, value in patch.totals.model_dump(exclude_none=True).items():
            setattr(state.totals, field, value)


def retry_failed_checks(
    state: ReconcileState,
    *,
    tolerance: float = 0.01,
    max_retries: int = 3,
    client: OpenAI | None = None,
    model: str = DEFAULT_AGNES_MODEL,
) -> ReconcileState:
    """Retry until Python reports all checks ok or three attempts are exhausted.

    Args:
        state: Mutable active reconciliation state to check and update.
        tolerance: Maximum allowed absolute numeric delta.
        max_retries: Requested retry count, clamped to the range zero through three.
        client: Optional Agnes-compatible client for tests or custom callers.
        model: Agnes model identifier.

    Returns:
        The same state object with latest checks and serialized retry attempts.

    Raises:
        ValueError: If the provider retry patch cannot satisfy its schema.

    Notes:
        Python reruns every deterministic check after a patch. A model response
        never independently marks the reconciliation successful.
    """
    retry_limit = min(max(max_retries, 0), 3)
    current = run_checks(_document_total(state.totals), state.items, tolerance=tolerance)
    state.checks = current.checks
    if current.is_valid or retry_limit == 0:
        return state

    active_client = client
    for attempt in range(1, retry_limit + 1):
        if current.is_valid:
            break
        if active_client is None:
            from src.agnes_client import get_agnes_client

            active_client = get_agnes_client()

        indices = current.failing_row_indices
        rows = [
            {"row_index": index, **state.items[index].model_dump()}
            for index in indices
            if 0 <= index < len(state.items)
        ]
        sum_message = _sum_message(state.items, state.totals)
        failed_before = [check.model_dump() for check in current.checks if not check.ok]
        patch = _request_patch(active_client, model, rows, state.totals, sum_message)
        _merge_patch(state, patch)
        current = run_checks(_document_total(state.totals), state.items, tolerance=tolerance)
        state.checks = current.checks
        state.retries.append(
            {
                "attempt": attempt,
                "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                "model": model,
                "failed_checks": failed_before,
                "failing_rows": [_truncate_raw(row) for row in rows],
                "totals": state.totals.model_dump(),
                "numeric_error": sum_message,
                "patch": patch.model_dump(exclude_none=True),
                "checks_after": [check.model_dump() for check in current.checks],
                "all_ok": current.is_valid,
            }
        )
    return state


def retry_reconciliation_loop(
    doc_total: DocumentTotal,
    line_items: list[LineItem],
    tolerance: float = 0.01,
    max_retries: int = 3,
    client: OpenAI | None = None,
    model: str = DEFAULT_AGNES_MODEL,
    cache_path: str | None = str(DEFAULT_CACHE_PATH),
) -> tuple[DocumentTotal, list[LineItem], ReconciliationResult, list[RetryLogEntry]]:
    """Run the active retry loop through the compatibility tuple interface.

    Args:
        doc_total: Detailed compatibility total model to update in place.
        line_items: Compatibility line items to reconcile.
        tolerance: Maximum allowed absolute numeric delta.
        max_retries: Requested retry count, clamped downstream to three.
        client: Optional Agnes-compatible client for tests or custom callers.
        model: Agnes model identifier.
        cache_path: Optional JSON cache output path; ``None`` disables writing.

    Returns:
        Updated total, updated line items, final deterministic result, and
        compatibility-format retry log.

    Raises:
        ValueError: If an Agnes retry patch fails schema validation.
        OSError: If a configured cache path cannot be written.
    """
    state = ReconcileState(
        items=line_items,
        totals=DocumentTotals(
            subtotal=doc_total.subtotal,
            tax=doc_total.tax,
            total=doc_total.total,
            page=doc_total.page,
        ),
    )
    retry_failed_checks(
        state,
        tolerance=tolerance,
        max_retries=max_retries,
        client=client,
        model=model,
    )
    doc_total.subtotal = state.totals.subtotal
    doc_total.tax = state.totals.tax
    doc_total.total = state.totals.total
    doc_total.page = state.totals.page
    final = run_checks(doc_total, state.items, tolerance=tolerance)
    logs = [
        RetryLogEntry(
            attempt=entry["attempt"],
            timestamp=entry["timestamp"],
            model_used=entry["model"],
            failing_rows_sent=entry["failing_rows"],
            numeric_errors_sent=[entry["numeric_error"]],
            patch_received=entry["patch"],
            resolved=entry["all_ok"],
            notes="Python reran deterministic checks after this patch.",
        )
        for entry in state.retries
    ]
    if cache_path:
        path = Path(cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return doc_total, state.items, final, logs
