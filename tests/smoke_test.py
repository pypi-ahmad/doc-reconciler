"""Smoke test suite covering Pydantic models, deterministic checks, and live Agnes retry loop."""

import os
import sys

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pymupdf
from src.models import (
    CheckResult,
    DocumentTotal,
    LineItem,
    ReconciliationResult,
    ExtractionPayload,
)
from src.pdf_processor import PDFDocument
from src.checks import check_document, run_checks
from src.extract import extract_from_text
from src.retry import retry_reconciliation_loop
from src.agnes_client import DEFAULT_AGNES_MODEL, get_agnes_client, get_available_providers


def test_models_and_checks() -> None:
    print("[1/5] Testing Pydantic models (LineItem, DocumentTotal, CheckResult)...")
    item1 = LineItem(
        qty=1.0,
        unit_price=10.0,
        amount=10.0,
        page=1,
        raw="1. Standard Widget | Qty: 1 | Unit Price: $10.00 | Amount: $10.00",
        description="Standard Widget",
    )
    # Intentional math error on item 2 to test deterministic checker
    item2 = LineItem(
        qty=1.0,
        unit_price=15.0,
        amount=14.0,  # 1 x 15 = 15, not 14
        page=1,
        raw="2. Premium Gadget | Qty: 1 | Unit Price: $15.00 | Amount: $14.00",
        description="Premium Gadget",
    )

    doc_total = DocumentTotal(
        subtotal=25.0,
        tax=0.0,
        shipping=0.0,
        discount=0.0,
        total=26.0,
        currency="USD",
        page=1,
        page_totals={1: 26.0},
        raw="Subtotal $26, Total $26",
    )

    assert item1.qty == 1.0
    assert item2.amount == 14.0
    print(" -> Models validated.")

    print("[2/5] Testing deterministic checks (no LLM)...")
    results = check_document(doc_total, [item1, item2], tolerance=0.01)
    res_obj = run_checks(doc_total, [item1, item2], tolerance=0.01)
    assert not res_obj.is_valid, "Expected validation to fail due to deliberate mismatches"
    assert len(res_obj.discrepancies) > 0
    print(f" -> Found {len(res_obj.discrepancies)} expected discrepancies:")
    for d in res_obj.discrepancies:
        print(f"    * {d}")

    # Now fix item2 and verify arithmetic passing
    item2_fixed = LineItem(
        qty=1.0,
        unit_price=15.0,
        amount=15.0,
        page=1,
        raw="2. Premium Gadget | Qty: 1 | Unit Price: $15.00 | Amount: $15.00",
        description="Premium Gadget",
    )
    doc_total_fixed = DocumentTotal(
        subtotal=25.0,
        tax=0.0,
        shipping=0.0,
        discount=0.0,
        total=25.0,
        currency="USD",
        page=1,
        page_totals={1: 25.0},
    )
    res_fixed = run_checks(doc_total_fixed, [item1, item2_fixed], tolerance=0.01)
    assert res_fixed.is_valid
    print(" -> Fixed data successfully passes all deterministic checks.")

    print("[3/5] Testing multi-page PyMuPDF integration...")
    doc = pymupdf.open()
    page1 = doc.new_page()
    page1.insert_text((50, 72), "Invoice #1001\nPage 1\nItem: Widget A, Qty: 5, Price: $20.00, Amount: $100.00")
    page2 = doc.new_page()
    page2.insert_text((50, 72), "Invoice #1001\nPage 2\nItem: Widget B, Qty: 2, Price: $15.00, Amount: $30.00\nSubtotal: $130.00, Total: $145.00")

    pdf_bytes = doc.tobytes()
    doc.close()

    wrapped = PDFDocument(pdf_bytes, filename="test_multipage.pdf")
    assert wrapped.page_count == 2
    pages = wrapped.get_all_pages_text()
    assert len(pages) == 2
    assert "Widget A" in pages[0]["text"]
    assert "Widget B" in pages[1]["text"]

    img = wrapped.render_page_image(0, dpi=72)
    assert img.size[0] > 0 and img.size[1] > 0
    wrapped.close()
    print(" -> PyMuPDF multi-page extraction and rendering verified.")

    print("[4/5] Testing provider detection...")
    providers = get_available_providers()
    print(f" -> Detected {len(providers)} provider option(s).")
    for p in providers:
        print(f"    * {p.display_name} (Base URL: {p.base_url or 'default'})")

    print("[5/5] Testing deliberate sum mismatch fixture and Agnes retry loop...")
    fixture_path = os.path.join("data", "fixtures", "invoice_mismatch.txt")
    assert os.path.exists(fixture_path), f"Fixture not found at {fixture_path}"

    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture_text = f.read()

    client = get_agnes_client()

    # Live Agnes extraction
    ext_total, ext_items = extract_from_text(
        raw_text=fixture_text,
        client=client,
        model=DEFAULT_AGNES_MODEL,
    )
    assert len(ext_items) >= 2, "Expected at least 2 line items"

    # Deterministic checks MUST fail on the deliberate mismatch (10+15=25 vs printed 26)
    initial_check = run_checks(ext_total, ext_items, tolerance=0.01)
    assert not initial_check.is_valid, "Expected checks to fail on deliberate mismatch fixture"
    print(f" -> Initial checks correctly failed with numeric errors: {initial_check.numeric_errors}")

    # Retry loop executes with only failing rows + numeric discrepancy
    cache_path = os.path.join("data", "cache", "last_reconcile.json")
    _, _, final_check, retry_log = retry_reconciliation_loop(
        doc_total=ext_total,
        line_items=ext_items,
        tolerance=0.01,
        max_retries=3,
        client=client,
        model=DEFAULT_AGNES_MODEL,
        cache_path=cache_path,
    )
    assert len(retry_log) > 0, "Expected retry loop to execute at least 1 attempt"
    print(f" -> Retry loop ran {len(retry_log)} attempt(s).")
    for log in retry_log:
        print(f"    * Attempt {log.attempt}: errors sent={log.numeric_errors_sent}, rows sent={len(log.failing_rows_sent)}")

    assert os.path.exists(cache_path), f"Cache file {cache_path} missing"
    print("\nAll smoke tests passed successfully!")


if __name__ == "__main__":
    test_models_and_checks()
