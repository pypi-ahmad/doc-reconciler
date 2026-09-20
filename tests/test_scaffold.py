"""Requested scaffold contract checks."""

from pathlib import Path

from src.config import get_settings
from src.models import CheckResult, DocumentTotals, LineItem, ReconcileState


def test_models_and_fixture_contract() -> None:
    item = LineItem(desc="Line A", qty=1, unit_price=10, amount=10, page=1, raw="Line A")
    totals = DocumentTotals(subtotal=25, tax=0, total=26, page=1)
    check = CheckResult(name="sum", ok=False, expected=25, actual=26, delta=-1, detail="mismatch")
    state = ReconcileState(items=[item], totals=totals, checks=[check], texts=["Invoice 1042"])

    assert state.items[0].desc == "Line A"
    assert state.checks[0].ok is False
    assert get_settings().max_retries == 3
    assert Path("data/fixtures/invoice_mismatch.txt").read_text(encoding="utf-8") == (
        "Invoice 1042\n"
        "Line A  qty 1  unit 10.00  amount 10.00\n"
        "Line B  qty 1  unit 15.00  amount 15.00\n"
        "Total 26.00\n"
    )
