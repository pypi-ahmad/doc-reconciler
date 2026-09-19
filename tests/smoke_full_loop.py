"""Smoke the full loop against Agnes until data/cache/last_reconcile.json exists

and shows at least one failed check then a retry entry.
"""

from __future__ import annotations

import json
import os
import sys

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import DocumentTotal, LineItem, CheckResult, ReconciliationResult
from src.extract import extract_from_text
from src.checks import check_document, run_checks
from src.retry import retry_reconciliation_loop
from src.agnes_client import DEFAULT_AGNES_MODEL, get_agnes_client


def main():
    print("=" * 60)
    print("Smoking Full Loop against Agnes AI")
    print("=" * 60)

    # 1. Check API Key
    client = get_agnes_client()
    print("[1/5] Agnes client initialized with user AGNESAI_API_KEY.")

    # 2. Load text fixture with deliberate mismatch (10+15=25 vs total 26)
    fixture_path = os.path.join("data", "fixtures", "invoice_mismatch.txt")
    assert os.path.exists(fixture_path), f"Fixture not found: {fixture_path}"

    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture_text = f.read()

    print(f"[2/5] Loaded fixture from {fixture_path}:\n{fixture_text.strip()}")

    # 3. Call Agnes AI to extract line items and stated totals
    print("\n[3/5] Calling Agnes AI (agnes-3.0-flash) to extract line items & totals...")
    doc_total, line_items = extract_from_text(
        raw_text=fixture_text,
        client=client,
        model=DEFAULT_AGNES_MODEL,
    )

    print(f" -> Extracted {len(line_items)} line items:")
    for idx, it in enumerate(line_items):
        print(f"    Item {idx}: '{it.description}' | Qty: {it.qty} | Price: {it.unit_price} | Amount: {it.amount}")
    print(f" -> Stated Total: {doc_total.total}")

    assert len(line_items) >= 2, f"Expected at least 2 line items, got {len(line_items)}"

    # 4. Run deterministic checks (no LLM)
    print("\n[4/5] Running deterministic checks in src/checks.py (no LLM)...")
    check_results: list[CheckResult] = check_document(doc_total, line_items, tolerance=0.01)
    reconcile_res = run_checks(doc_total, line_items, tolerance=0.01)

    print(f" -> Checks evaluated: {len(check_results)}")
    for c in check_results:
        status_sym = "PASS" if c.passed else "FAIL"
        print(f"    [{status_sym}] {c.name}: {c.message}")

    # Must fail on the deliberate mismatch
    assert not reconcile_res.is_valid, "Expected initial check to fail on deliberate mismatch (10+15=25 vs 26)!"
    assert any(not c.passed for c in check_results), "Expected at least one check to fail!"
    print(f" -> Verified: Initial check correctly failed with errors: {reconcile_res.numeric_errors}")

    # 5. Call Agnes retry loop with only failing rows and numeric discrepancy
    cache_path = os.path.join("data", "cache", "last_reconcile.json")
    if os.path.exists(cache_path):
        os.remove(cache_path)

    print("\n[5/5] Calling retry_reconciliation_loop (max 3 retries)...")
    final_tot, final_items, final_res, retry_log = retry_reconciliation_loop(
        doc_total=doc_total,
        line_items=line_items,
        tolerance=0.01,
        max_retries=3,
        client=client,
        model=DEFAULT_AGNES_MODEL,
        cache_path=cache_path,
    )

    print(f" -> Retry loop finished with {len(retry_log)} attempt(s).")
    for entry in retry_log:
        print(f"    Attempt #{entry.attempt}:")
        print(f"      Failing rows sent: {len(entry.failing_rows_sent)}")
        print(f"      Numeric error sent: {entry.numeric_errors_sent}")
        print(f"      Patch received: {entry.patch_received}")
        print(f"      Resolved: {entry.resolved}")

    # 6. Verify data/cache/last_reconcile.json exists and shows at least one failed check then a retry entry
    assert os.path.exists(cache_path), f"Expected cache file {cache_path} to exist!"
    with open(cache_path, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    print(f"\n[CACHE AUDIT VERIFICATION]")
    print(f"Cache file path: {cache_path}")
    print(f"Initial failed checks count: {len(cache_data.get('initial_failed_checks', []))}")
    print(f"Retry entries count: {len(cache_data.get('retry_entries', []))}")

    assert len(cache_data.get("initial_failed_checks", [])) >= 1, "Expected at least one failed check in cache!"
    assert len(cache_data.get("retry_entries", [])) >= 1, "Expected at least one retry entry in cache!"

    print("\nSUCCESS: data/cache/last_reconcile.json exists and confirms failed check + retry entry!")


if __name__ == "__main__":
    main()
