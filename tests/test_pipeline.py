"""Offline full-pipeline test with a fake OpenAI-compatible client."""

import json
from types import SimpleNamespace

from src.pipeline import reconcile_document


class FakeCompletions:
    def __init__(self) -> None:
        self.responses = [
            {
                "items": [
                    {
                        "desc": "Line A",
                        "qty": 1,
                        "unit_price": 10,
                        "amount": 10,
                        "page": 1,
                        "raw": "Line A",
                    },
                    {
                        "desc": "Line B",
                        "qty": 1,
                        "unit_price": 15,
                        "amount": 15,
                        "page": 1,
                        "raw": "Line B",
                    },
                ],
                "totals": {"subtotal": None, "tax": None, "total": 26, "page": 1},
                "notes": "",
            },
            {"items": None, "totals": {"total": 25}},
        ]
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.requests.append(kwargs)
        content = json.dumps(self.responses.pop(0))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_pipeline_rechecks_patch_with_python() -> None:
    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    state = reconcile_document(
        "data/fixtures/invoice_mismatch.txt",
        client=client,
        max_retries=3,
    )

    assert state.retries[0]["failed_checks"]
    assert state.retries[0]["numeric_error"] == ("sum(items)=25.00 stated_total=26.00 delta=-1.00")
    assert all(check.ok for check in state.checks)
    assert len(completions.requests) == 2
