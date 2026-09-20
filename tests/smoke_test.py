"""Offline smoke checks for deterministic math and native PDF processing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.checks import run_checks
from src.models import DocumentTotal, LineItem
from src.pdf_processor import PDFDocument


def main() -> None:
    items = [
        LineItem(description="Widget", qty=1, unit_price=10, amount=10),
        LineItem(description="Service", qty=1, unit_price=15, amount=15),
    ]
    total = DocumentTotal(subtotal=25, total=26, tax=0, shipping=0, discount=0)
    failed = run_checks(total, items)
    assert not failed.is_valid
    assert any("delta=-1.00" in error for error in failed.numeric_errors)

    total.total = 25
    assert run_checks(total, items).is_valid

    fixture = Path("data/fixtures/invoice_mismatch.pdf")
    with PDFDocument(fixture) as document:
        assert document.pdf_type == "text_based"
        assert document.page_count == 2
        assert "Managed Hosting" in document.get_page_text(0)
        assert document.render_page_image(0).width > 0

    print("Offline smoke passed: deterministic deltas and pdf-inspector native route verified.")


if __name__ == "__main__":
    main()
