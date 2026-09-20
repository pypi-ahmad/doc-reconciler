"""Extraction and retry tests with a local fake OpenAI-compatible client."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.checks import run_checks
from src.extract import extract_from_text
from src.retry import retry_reconciliation_loop


class FakeCompletions:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.requests.append(kwargs)
        content = json.dumps(self.responses.pop(0))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class FakeClient:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


def test_extraction_then_python_verified_retry(tmp_path) -> None:
    client = FakeClient(
        [
            {
                "line_items": [
                    {
                        "description": "Widget",
                        "qty": 1,
                        "unit_price": 10,
                        "amount": 10,
                        "raw": "Widget 1 x 10 = 10",
                    },
                    {
                        "description": "Service",
                        "qty": 1,
                        "unit_price": 15,
                        "amount": 15,
                        "raw": "Service 1 x 15 = 15",
                    },
                ],
                "page_total": 26,
                "subtotal": 25,
                "tax": 0,
                "shipping": 0,
                "discount": 0,
                "grand_total": 26,
                "currency": "USD",
            },
            {
                "items": None,
                "totals": {"subtotal": None, "tax": None, "total": 25, "page": 1},
            },
        ]
    )
    total, items = extract_from_text("fixture", client=client)
    initial = run_checks(total, items)
    assert not initial.is_valid
    assert "items_sum_vs_total expected=25.00 actual=26.00 delta=-1.00" in initial.numeric_errors

    cache_path = tmp_path / "last_reconcile.json"
    total, items, final, log = retry_reconciliation_loop(
        total,
        items,
        client=client,
        max_retries=99,
        cache_path=str(cache_path),
    )
    assert final.is_valid
    assert len(log) == 1
    assert cache_path.exists()
    retry_prompt = client.completions.requests[1]["messages"][1]["content"]
    assert "delta=-1.00" in retry_prompt


def test_checks_module_has_no_llm_import() -> None:
    source = Path("src/checks.py").read_text(encoding="utf-8")
    assert "openai" not in source.lower()
