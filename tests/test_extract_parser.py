"""Hardened Agnes JSON parser tests."""

import pytest

from src.extract import parse_extraction


def test_parser_handles_fences_prose_and_currency_strings() -> None:
    result = parse_extraction(
        """Result follows:
```json
{
  "items": [
    {"desc": "Line A", "qty": "1", "unit_price": "$10.00", "amount": "10.00", "page": "1", "raw": "A"},
    {"desc": "Line B", "qty": 1, "unit_price": "15.00", "amount": "$15.00", "page": 1, "raw": "B"}
  ],
  "totals": {"subtotal": null, "tax": null, "total": "$26.00", "page": "1"},
  "notes": "stated mismatch"
}
```
"""
    )
    assert [item.amount for item in result.items] == [10.0, 15.0]
    assert result.totals.total == 26.0


def test_parser_rejects_missing_items_array() -> None:
    with pytest.raises(TypeError, match="items array"):
        parse_extraction('{"totals": {"total": 26}, "notes": ""}')
