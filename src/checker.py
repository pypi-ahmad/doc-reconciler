"""Deterministic Python mathematical checks for document reconciliation (Option B).

Delegates to src/checks.py for unified check logic.
"""

from __future__ import annotations

from typing import List
from src.models import DocumentTotal, LineItem, ReconciliationResult
from src.checks import run_checks


def run_deterministic_checks(
    doc_total: DocumentTotal,
    line_items: List[LineItem],
    tolerance: float = 0.01,
) -> ReconciliationResult:
    """Execute mathematical and integrity checks across extracted document figures.

    Delegates to src.checks.run_checks (no LLM).
    """
    return run_checks(doc_total, line_items, tolerance=tolerance)
