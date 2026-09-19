"""End-to-end test hitting Agnes AI for extraction, deterministic checks, and retry loop."""

import os
import sys

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.pdf_processor import PDFDocument
from src.extract import extract_and_merge_document
from src.checks import run_checks
from src.retry import retry_reconciliation_loop
from src.providers import get_available_providers, get_openai_client


def main():
    print("=" * 60)
    print("Running Option B: Extract -> Checks -> Agnes Retry Loop")
    print("=" * 60)

    # 1. Check provider availability
    providers = get_available_providers()
    assert providers, "No providers found. Ensure AGNESAI_API_KEY is configured."
    agnes_opt = next((p for p in providers if p.provider == "Agnes AI"), providers[0])
    print(f"[1/5] Selected provider: {agnes_opt.display_name}")
    client = get_openai_client(agnes_opt)

    # 2. Load PDF fixture
    pdf_path = os.path.join("data", "fixtures", "invoice_mismatch.pdf")
    assert os.path.exists(pdf_path), f"Fixture not found at {pdf_path}"
    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    pdf_doc = PDFDocument(file_bytes, filename="invoice_mismatch.pdf")
    pages = pdf_doc.get_all_pages_text()
    print(f"[2/5] Loaded PDF fixture: {len(pages)} pages detected.")

    # 3. Hit Agnes AI to extract line items per page and merge
    print("[3/5] Calling Agnes AI to extract per-page line items and merge...")
    doc_total, line_items = extract_and_merge_document(
        pages=pages,
        client=client,
        model=agnes_opt.model_id,
    )

    print(f" -> Extracted {len(line_items)} line items across {len(pages)} pages.")
    for idx, it in enumerate(line_items):
        print(f"    Item {idx}: Page {it.page} | '{it.description}' | Qty: {it.qty} | Price: {it.unit_price} | Amount: {it.amount}")
    print(f" -> Extracted Document Total: {doc_total.total} (Page totals: {doc_total.page_totals})")

    # 4. Run deterministic checks (no LLM)
    print("[4/5] Running deterministic Python checks...")
    initial_check = run_checks(doc_total, line_items, tolerance=0.01)
    print(f" -> Initial checks passed: {initial_check.is_valid}")
    print(f" -> Numeric errors detected: {initial_check.numeric_errors}")
    print(f" -> Failing row indices: {initial_check.failing_row_indices}")
    print(f" -> Discrepancies ({len(initial_check.discrepancies)}):")
    for d in initial_check.discrepancies:
        print(f"    * {d}")

    assert not initial_check.is_valid, "Expected initial checks to FAIL on invoice_mismatch.pdf!"
    assert len(initial_check.numeric_errors) > 0 or len(initial_check.discrepancies) > 0

    # 5. Execute Option B retry loop with Agnes
    print("[5/5] Executing retry loop with Agnes AI (sending only failing rows + numeric error)...")
    final_total, final_items, final_check, retry_log = retry_reconciliation_loop(
        doc_total=doc_total,
        line_items=line_items,
        tolerance=0.01,
        max_retries=3,
        client=client,
        model=agnes_opt.model_id,
    )

    print(f" -> Retry loop completed with {len(retry_log)} attempt(s).")
    for log in retry_log:
        print(f"\n[RETRY LOG ATTEMPT #{log.attempt}]")
        print(f"Timestamp: {log.timestamp}")
        print(f"Model: {log.model_used}")
        print(f"Numeric Errors Sent:\n  {log.numeric_errors_sent}")
        print(f"Failing Rows Sent: {len(log.failing_rows_sent)} row(s)")
        print(f"Patch Received:\n  {log.patch_received}")
        print(f"Resolved: {log.resolved}")
        print(f"Notes: {log.notes}")

    print("\n[FINAL RECONCILIATION RESULT]")
    print(f"Valid: {final_check.is_valid}")
    print(f"Remaining Discrepancies: {final_check.discrepancies}")
    print("\nEnd-to-end extract and retry test finished successfully!")


if __name__ == "__main__":
    main()
