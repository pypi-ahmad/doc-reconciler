"""Live full-pipeline smoke against Agnes."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.pipeline import reconcile_document


def main() -> None:
    fixture = REPO_ROOT / "data" / "fixtures" / "invoice_mismatch.txt"
    cache = REPO_ROOT / "data" / "cache" / "last_reconcile.json"
    state = reconcile_document(fixture, tolerance=0.01, max_retries=3)

    assert state.retries, "Expected at least one retry entry."
    assert any(not check["ok"] for retry in state.retries for check in retry["failed_checks"]), (
        "Expected at least one recorded failed check."
    )

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    final_ok = all(bool(check.ok) for check in state.checks)
    print(f"Reconcile smoke passed: retries={len(state.retries)} final_ok={final_ok}; {cache}")


if __name__ == "__main__":
    main()
