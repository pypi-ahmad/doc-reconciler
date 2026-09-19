"""Deterministic Python checks for document reconciliation (no LLM)."""

from __future__ import annotations

from collections import defaultdict
from typing import List, Optional, Set, Tuple
from src.models import (
    CheckResult,
    DocumentTotal,
    LineItem,
    ReconciliationResult,
)


def check_document(
    doc_total: DocumentTotal,
    line_items: List[LineItem],
    tolerance: float = 0.01,
) -> List[CheckResult]:
    """Execute deterministic mathematical checks across extracted document figures.

    Returns a list of CheckResult without any LLM calls.
    """
    res = run_checks(doc_total, line_items, tolerance=tolerance)
    return res.checks


def run_checks(
    doc_total: DocumentTotal,
    line_items: List[LineItem],
    tolerance: float = 0.01,
) -> ReconciliationResult:
    """Run deterministic mathematical and integrity checks.

    Checks:
    1. sum(items.amount) vs stated total (tolerance slider, default 0.01)
    2. qty * unit_price vs amount for each line item
    3. duplicate rows (descriptions or exact row duplication)
    4. page-1 total vs last-page total if both exist
    """
    checks: List[CheckResult] = []
    failing_indices: Set[int] = set()
    numeric_errors: List[str] = []
    discrepancies: List[str] = []

    # -------------------------------------------------------------------------
    # Check 1: sum(items.amount) vs stated total
    # -------------------------------------------------------------------------
    stated_total = doc_total.total if doc_total.total is not None else doc_total.subtotal
    if stated_total is not None and line_items:
        items_with_amount = [it for it in line_items if it.amount is not None]
        calculated_sum = round(sum(it.amount for it in items_with_amount if it.amount is not None), 2)
        delta = round(calculated_sum - stated_total, 2)
        passed = abs(delta) <= tolerance
        num_err = f"sum={calculated_sum:.2f} total={stated_total:.2f} delta={delta:+.2f}"

        if not passed:
            msg = f"Sum vs Stated Total mismatch: {num_err}"
            numeric_errors.append(num_err)
            discrepancies.append(msg)
            # All items contribute to sum mismatch
            for i in range(len(line_items)):
                failing_indices.add(i)
        else:
            msg = f"Sum of line items ({calculated_sum:.2f}) matches stated total ({stated_total:.2f})."

        checks.append(
            CheckResult(
                name="Sum vs Stated Total",
                passed=passed,
                expected=stated_total,
                actual=calculated_sum,
                discrepancy_amount=abs(delta) if not passed else 0.0,
                numeric_error=num_err if not passed else None,
                message=msg,
            )
        )

    # -------------------------------------------------------------------------
    # Check 2: qty * unit_price vs amount for each line item
    # -------------------------------------------------------------------------
    for idx, item in enumerate(line_items):
        if item.qty is not None and item.unit_price is not None and item.amount is not None:
            expected_amt = round(item.qty * item.unit_price, 2)
            actual_amt = round(item.amount, 2)
            diff = round(actual_amt - expected_amt, 2)
            passed = abs(diff) <= tolerance
            desc_label = item.description.strip() if item.description else (item.raw.strip() or f"Row {idx}")

            if not passed:
                num_err = (
                    f"row={idx} qty={item.qty} unit_price={item.unit_price:.2f} "
                    f"calculated={expected_amt:.2f} stated={actual_amt:.2f} delta={diff:+.2f}"
                )
                msg = (
                    f"Row {idx} ('{desc_label[:25]}') math error: "
                    f"{item.qty} x {item.unit_price:.2f} = {expected_amt:.2f}, stated {actual_amt:.2f} (delta={diff:+.2f})"
                )
                failing_indices.add(idx)
                numeric_errors.append(num_err)
                discrepancies.append(msg)
            else:
                msg = f"Row {idx} verified: {item.qty} x {item.unit_price:.2f} = {actual_amt:.2f}"

            checks.append(
                CheckResult(
                    name=f"Row {idx} Math ({desc_label[:20]})",
                    passed=passed,
                    expected=expected_amt,
                    actual=actual_amt,
                    discrepancy_amount=abs(diff) if not passed else 0.0,
                    numeric_error=num_err if not passed else None,
                    message=msg,
                )
            )

    # -------------------------------------------------------------------------
    # Check 3: duplicate rows / descriptions
    # -------------------------------------------------------------------------
    desc_map: dict[str, list[int]] = defaultdict(list)
    for idx, item in enumerate(line_items):
        clean_desc = (item.description or "").strip().lower()
        if clean_desc and clean_desc not in {"item", "product", "service"}:
            desc_map[clean_desc].append(idx)

    dup_found = False
    for desc, indices in desc_map.items():
        if len(indices) > 1:
            dup_found = True
            msg = f"Duplicate rows detected for description '{desc}' across rows {indices}."
            discrepancies.append(msg)
            for idx in indices:
                failing_indices.add(idx)
            checks.append(
                CheckResult(
                    name=f"Duplicate Rows ('{desc[:20]}')",
                    passed=False,
                    message=msg,
                )
            )

    if not dup_found and line_items:
        checks.append(
            CheckResult(
                name="Duplicate Rows Check",
                passed=True,
                message="No duplicate rows or descriptions detected.",
            )
        )

    # -------------------------------------------------------------------------
    # Check 4: page-1 total vs last-page total if both exist
    # -------------------------------------------------------------------------
    if doc_total.page_totals:
        pages = sorted(doc_total.page_totals.keys())
        if len(pages) >= 2 and 1 in doc_total.page_totals:
            p1 = 1
            plast = pages[-1]
            p1_tot = round(doc_total.page_totals[p1], 2)
            plast_tot = round(doc_total.page_totals[plast], 2)
            delta = round(plast_tot - p1_tot, 2)
            passed = abs(delta) <= tolerance
            num_err = f"page-1 total={p1_tot:.2f} last-page total={plast_tot:.2f} delta={delta:+.2f}"

            if not passed:
                msg = f"Page-1 total ({p1_tot:.2f}) differs from last page {plast} total ({plast_tot:.2f}): {num_err}"
                numeric_errors.append(num_err)
                discrepancies.append(msg)
            else:
                msg = f"Page-1 total ({p1_tot:.2f}) matches last page {plast} total ({plast_tot:.2f})."

            checks.append(
                CheckResult(
                    name="First/Last Page Total Mismatch",
                    passed=passed,
                    expected=p1_tot,
                    actual=plast_tot,
                    discrepancy_amount=abs(delta) if not passed else 0.0,
                    numeric_error=num_err if not passed else None,
                    message=msg,
                )
            )

    all_passed = len(checks) > 0 and all(c.passed for c in checks)

    return ReconciliationResult(
        is_valid=all_passed,
        checks=checks,
        failing_row_indices=sorted(failing_indices),
        numeric_errors=numeric_errors,
        discrepancies=discrepancies,
    )
