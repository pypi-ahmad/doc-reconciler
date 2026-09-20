"""Offline deterministic-check smoke using the cached Agnes extraction."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.checks import run_checks
from src.models import DocumentTotal, ExtractionResult


def main() -> None:
    extract_cache = REPO_ROOT / "data" / "cache" / "last_extract.json"
    checks_cache = REPO_ROOT / "data" / "cache" / "last_checks.json"
    extraction = ExtractionResult.model_validate_json(extract_cache.read_text(encoding="utf-8"))
    totals = extraction.totals
    result = run_checks(
        DocumentTotal(
            subtotal=totals.subtotal,
            tax=totals.tax,
            total=totals.total,
            page=totals.page,
        ),
        extraction.items,
    )

    sum_check = next(check for check in result.checks if check.name == "items_sum_vs_total")
    assert sum_check.ok is False, "Fixture sum check unexpectedly passed; extraction is wrong."
    assert sum_check.delta is not None and abs(abs(sum_check.delta) - 1.0) < 0.001

    checks_cache.parent.mkdir(parents=True, exist_ok=True)
    checks_cache.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"Checks smoke passed: delta={sum_check.delta:+.2f}; {checks_cache}")


if __name__ == "__main__":
    main()
