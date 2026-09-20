"""Deterministic reconciliation checks. No LLM client belongs in this module."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from src.models import CheckResult, DocumentTotal, LineItem, ReconciliationResult

CENT = Decimal("0.01")


def _money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _numeric_check(
    name: str, expected: Decimal, actual: Decimal, tolerance: Decimal, detail: str
) -> CheckResult:
    """Build one check using delta = expected/calculated - actual/stated."""
    delta = (expected - actual).quantize(CENT)
    return CheckResult(
        name=name,
        ok=abs(delta) <= tolerance,
        expected=float(expected),
        actual=float(actual),
        delta=float(delta),
        detail=detail,
        discrepancy_amount=float(abs(delta)),
        numeric_error=(
            None
            if abs(delta) <= tolerance
            else f"{name} expected={expected:.2f} actual={actual:.2f} delta={delta:+.2f}"
        ),
    )


def check_document(
    doc_total: DocumentTotal,
    line_items: list[LineItem],
    tolerance: float = 0.01,
) -> list[CheckResult]:
    """Return individual deterministic checks for a document.

    Args:
        doc_total: Stated document totals to compare with line items.
        line_items: Extracted line items with quantities and stated amounts.
        tolerance: Maximum allowed absolute numeric delta.

    Returns:
        Individual check results without their aggregate reconciliation wrapper.
    """
    return run_checks(doc_total, line_items, tolerance=tolerance).checks


def run_checks(
    doc_total: DocumentTotal,
    line_items: list[LineItem],
    tolerance: float = 0.01,
    page_totals: dict[int, float] | None = None,
) -> ReconciliationResult:
    """Run sum, row multiplication, duplicate, and optional page-total checks.

    Args:
        doc_total: Stated document totals.
        line_items: Extracted rows to verify.
        tolerance: Maximum allowed absolute numeric delta.
        page_totals: Optional stated totals keyed by page number.

    Returns:
        Aggregate validity, individual results, failed row indices, and retry
        messages. Numeric deltas use ``expected - actual``.

    Examples:
        >>> result = run_checks(
        ...     DocumentTotal(total=26.0),
        ...     [
        ...         LineItem(desc="Line A", qty=1, unit_price=10, amount=10),
        ...         LineItem(desc="Line B", qty=1, unit_price=15, amount=15),
        ...     ],
        ... )
        >>> result.is_valid
        False
        >>> next(check.delta for check in result.checks if check.name == "items_sum_vs_total")
        -1.0
    """
    allowed_delta = Decimal(str(tolerance))
    checks: list[CheckResult] = []
    failing_indices: set[int] = set()

    if doc_total.total is None or not line_items or any(item.amount is None for item in line_items):
        items_sum = CheckResult(
            name="items_sum_vs_total",
            ok=False,
            detail="A stated total and every line amount are required.",
        )
    else:
        calculated = sum(
            (_money(item.amount) for item in line_items if item.amount is not None), Decimal("0.00")
        )
        items_sum = _numeric_check(
            "items_sum_vs_total",
            calculated,
            _money(doc_total.total),
            allowed_delta,
            "Calculated line-item sum compared with stated total.",
        )
    checks.append(items_sum)
    if not items_sum.ok:
        failing_indices.update(range(len(line_items)))

    for index, item in enumerate(line_items):
        if item.qty is None or item.unit_price is None or item.amount is None:
            row_check = CheckResult(
                name="qty_times_unit_vs_amount",
                ok=False,
                detail=f"Row {index} lacks qty, unit_price, or amount.",
            )
        else:
            calculated = _money(Decimal(str(item.qty)) * Decimal(str(item.unit_price)))
            row_check = _numeric_check(
                "qty_times_unit_vs_amount",
                calculated,
                _money(item.amount),
                allowed_delta,
                f"Row {index}: qty × unit price compared with stated amount.",
            )
        checks.append(row_check)
        if not row_check.ok:
            failing_indices.add(index)

    descriptions: dict[str, list[int]] = {}
    for index, item in enumerate(line_items):
        description = (item.desc or item.description or "").strip().casefold()
        if description:
            descriptions.setdefault(description, []).append(index)
    duplicate_rows = [indices for indices in descriptions.values() if len(indices) > 1]
    duplicate_indices = sorted(index for indices in duplicate_rows for index in indices)
    duplicate_check = CheckResult(
        name="duplicate_desc",
        ok=not duplicate_indices,
        detail=(
            "No duplicate descriptions found."
            if not duplicate_indices
            else f"Duplicate descriptions found on rows {duplicate_indices}."
        ),
    )
    checks.append(duplicate_check)
    failing_indices.update(duplicate_indices)

    stated_page_totals = page_totals or getattr(doc_total, "page_totals", {})
    if len(stated_page_totals) >= 2:
        ordered_pages = sorted(stated_page_totals)
        first_page = ordered_pages[0]
        last_page = ordered_pages[-1]
        checks.append(
            _numeric_check(
                "first_vs_last_total",
                _money(stated_page_totals[first_page]),
                _money(stated_page_totals[last_page]),
                allowed_delta,
                f"Page {first_page} total compared with page {last_page} total.",
            )
        )

    failed_checks = [check for check in checks if not check.ok]
    return ReconciliationResult(
        is_valid=not failed_checks,
        checks=checks,
        failing_row_indices=sorted(failing_indices),
        numeric_errors=[check.numeric_error for check in failed_checks if check.numeric_error],
        discrepancies=[check.detail for check in failed_checks],
    )
