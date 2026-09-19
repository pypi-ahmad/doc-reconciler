"""Retry reconciliation loop with Agnes AI targeting only failing rows and numeric errors."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from openai import OpenAI

from src.models import (
    DocumentTotal,
    LineItem,
    ReconciliationResult,
    RetryLogEntry,
)
from src.checks import run_checks
from src.agnes_client import DEFAULT_AGNES_MODEL, get_agnes_client


def clean_json_text(text: str) -> str:
    """Strip markdown code fence blocks if present."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def save_last_reconcile_cache(
    initial_result: ReconciliationResult,
    final_result: ReconciliationResult,
    doc_total: DocumentTotal,
    line_items: List[LineItem],
    retry_log: List[RetryLogEntry],
    cache_path: str = os.path.join("data", "cache", "last_reconcile.json"),
) -> None:
    """Save reconciliation audit state to data/cache/last_reconcile.json."""
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    payload = {
        "timestamp": datetime.now().isoformat(),
        "is_valid": final_result.is_valid,
        "initial_failed_checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "expected": c.expected,
                "actual": c.actual,
                "numeric_error": c.numeric_error,
                "message": c.message,
            }
            for c in initial_result.checks
            if not c.passed
        ],
        "initial_numeric_errors": initial_result.numeric_errors,
        "retry_entries": [
            {
                "attempt": entry.attempt,
                "timestamp": entry.timestamp,
                "model_used": entry.model_used,
                "failing_rows_sent": entry.failing_rows_sent,
                "numeric_errors_sent": entry.numeric_errors_sent,
                "patch_received": entry.patch_received,
                "resolved": entry.resolved,
                "notes": entry.notes,
            }
            for entry in retry_log
        ],
        "final_checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "numeric_error": c.numeric_error,
                "message": c.message,
            }
            for c in final_result.checks
        ],
        "doc_total": doc_total.model_dump(),
        "line_items": [it.model_dump() for it in line_items],
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def retry_reconciliation_loop(
    doc_total: DocumentTotal,
    line_items: List[LineItem],
    tolerance: float = 0.01,
    max_retries: int = 3,
    client: Optional[OpenAI] = None,
    model: str = DEFAULT_AGNES_MODEL,
    cache_path: Optional[str] = os.path.join("data", "cache", "last_reconcile.json"),
) -> Tuple[DocumentTotal, List[LineItem], ReconciliationResult, List[RetryLogEntry]]:
    """Execute Option B feedback loop:

    Sends Agnes ONLY the failing rows + the exact numeric error (e.g. "sum=12.40 total=13.00 delta=-0.60").
    Requests a corrected JSON patch, applies it, and re-runs checks. Up to max_retries (3).
    """
    if client is None:
        client = get_agnes_client()

    # 1. Initial deterministic check
    initial_result = run_checks(doc_total, line_items, tolerance=tolerance)
    current_result = initial_result
    retry_log: List[RetryLogEntry] = []

    if current_result.is_valid:
        if cache_path:
            save_last_reconcile_cache(
                initial_result=initial_result,
                final_result=current_result,
                doc_total=doc_total,
                line_items=line_items,
                retry_log=retry_log,
                cache_path=cache_path,
            )
        return doc_total, line_items, current_result, retry_log

    # 2. Retry loop up to max_retries
    for attempt in range(1, max_retries + 1):
        failing_indices = current_result.failing_row_indices
        if not failing_indices:
            failing_indices = list(range(len(line_items)))

        failing_rows_payload: List[Dict[str, Any]] = [
            {
                "row_index": idx,
                "page": line_items[idx].page,
                "description": line_items[idx].description,
                "qty": line_items[idx].qty,
                "unit_price": line_items[idx].unit_price,
                "amount": line_items[idx].amount,
                "raw": line_items[idx].raw,
            }
            for idx in failing_indices
            if 0 <= idx < len(line_items)
        ]

        numeric_error_text = "\n".join(current_result.numeric_errors) or "; ".join(current_result.discrepancies)

        system_prompt = (
            "You are a precise financial data reconciliation specialist.\n"
            "Deterministic checks flagged arithmetic or consistency errors on this document extraction.\n"
            "You are provided ONLY the failing rows and the exact numeric error.\n"
            "Re-evaluate the raw snippets, verify arithmetic (qty * unit_price == amount, sum(amounts) == total),\n"
            "and output a JSON patch to correct the failing rows and/or document total.\n"
            "Return ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "corrected_rows": [\n'
            "    {\n"
            '      "row_index": <int>,\n'
            '      "description": "<corrected description>",\n'
            '      "qty": <float>,\n'
            '      "unit_price": <float>,\n'
            '      "amount": <float>\n'
            "    }\n"
            "  ],\n"
            '  "corrected_total": <float or null>,\n'
            '  "explanation": "<brief reason for correction>"\n'
            "}"
        )

        user_prompt = (
            f"Numeric Errors Detected:\n{numeric_error_text}\n\n"
            f"Failing Rows Provided:\n{json.dumps(failing_rows_payload, indent=2)}\n\n"
            "Current Stated Total: "
            f"{doc_total.total}\n\n"
            "Please return the JSON patch with corrected row values so all mathematical checks pass."
        )

        response = None
        for r_attempt in range(4):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                )
                break
            except Exception as e:
                if "rate limit" in str(e).lower() and r_attempt < 3:
                    time.sleep((r_attempt + 1) * 3)
                    continue
                raise

        content = response.choices[0].message.content or "{}" if response else "{}"
        cleaned = clean_json_text(content)

        patch_dict: Dict[str, Any] = {}
        try:
            patch_dict = json.loads(cleaned)
        except json.JSONDecodeError:
            patch_dict = {"explanation": "Invalid JSON returned by model", "corrected_rows": []}

        # Apply patch to line items
        for corr in patch_dict.get("corrected_rows", []):
            try:
                r_idx = int(corr["row_index"])
                if 0 <= r_idx < len(line_items):
                    if corr.get("qty") is not None:
                        line_items[r_idx].qty = float(corr["qty"])
                    if corr.get("unit_price") is not None:
                        line_items[r_idx].unit_price = float(corr["unit_price"])
                    if corr.get("amount") is not None:
                        line_items[r_idx].amount = float(corr["amount"])
                    if corr.get("description"):
                        line_items[r_idx].description = str(corr["description"])
            except (ValueError, KeyError, TypeError):
                continue

        # Apply patch to total if specified
        if patch_dict.get("corrected_total") is not None:
            try:
                doc_total.total = float(patch_dict["corrected_total"])
            except (ValueError, TypeError):
                pass

        # Re-run checks
        new_result = run_checks(doc_total, line_items, tolerance=tolerance)

        log_entry = RetryLogEntry(
            attempt=attempt,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            model_used=model,
            failing_rows_sent=failing_rows_payload,
            numeric_errors_sent=current_result.numeric_errors,
            patch_received=patch_dict,
            resolved=new_result.is_valid,
            notes=f"Attempt {attempt}: {patch_dict.get('explanation', 'Patch applied')}. Result valid: {new_result.is_valid}",
        )
        retry_log.append(log_entry)

        current_result = new_result
        if current_result.is_valid:
            break

    # Save to cache file
    if cache_path:
        save_last_reconcile_cache(
            initial_result=initial_result,
            final_result=current_result,
            doc_total=doc_total,
            line_items=line_items,
            retry_log=retry_log,
            cache_path=cache_path,
        )

    return doc_total, line_items, current_result, retry_log
