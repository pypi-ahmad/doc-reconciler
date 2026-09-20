"""Deterministic Python mathematical checks for document reconciliation (Option B).

Delegates to src/checks.py for unified check logic.
"""

from __future__ import annotations

from src.checks import run_checks
from src.models import DocumentTotal, LineItem, ReconciliationResult


def run_deterministic_checks(
    doc_total: DocumentTotal,
    line_items: list[LineItem],
    tolerance: float = 0.01,
) -> ReconciliationResult:
    """Run compatibility checks by delegating to the active deterministic engine.

    Args:
        doc_total: Stated document totals in the compatibility model.
        line_items: Extracted line items to validate.
        tolerance: Maximum allowed absolute numeric delta.

    Returns:
        Deterministic reconciliation results from ``src.checks.run_checks``.
    """
    return run_checks(doc_total, line_items, tolerance=tolerance)
