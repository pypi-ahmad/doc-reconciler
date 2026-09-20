# Zero to Mastery

Start by running the app, then trace its flow and make a small, safe extension.
The stages follow the same boundaries used by the application.

## Stage 1: Learn the contract

Python owns the math. Agnes can extract stated values and propose a JSON patch,
but `src/checks.py` decides whether a document reconciles.

```text
10.00 + 15.00 = 25.00
stated total  = 26.00
delta         = -1.00
```

Start with [Onboarding](ONBOARDING.md) if you have not run the fixture.

## Stage 2: Trace the data flow

1. [`ingest_document`](../src/ingest.py) returns native or OCR-routed text.
2. [`extract_text`](../src/extract.py) asks Agnes for items and stated totals.
3. [`run_checks`](../src/checks.py) computes deterministic results.
4. [`retry_failed_checks`](../src/retry.py) sends failure context and re-runs
   checks after every patch.
5. [`reconcile_document`](../src/pipeline.py) coordinates the end-to-end flow.

Read [Architecture](ARCHITECTURE.md) alongside these modules. The retry limit is
three, and a remaining discrepancy is a valid final result.

## Stage 3: Run a deterministic check yourself

This example needs no key, network, PDF, or Ollama service:

```python
from src.checks import run_checks
from src.models import DocumentTotal, LineItem

result = run_checks(
    DocumentTotal(total=26.00),
    [
        LineItem(desc="Line A", qty=1, unit_price=10.00, amount=10.00),
        LineItem(desc="Line B", qty=1, unit_price=15.00, amount=15.00),
    ],
)

sum_check = next(check for check in result.checks if check.name == "items_sum_vs_total")
assert (sum_check.ok, sum_check.delta) == (False, -1.0)
```

The retry loop runs this same check after every Agnes patch. Review the formulas
in [Checks](CHECKS.md).

## Stage 4: Understand OCR routing

Text files always use the native route. A text-based PDF uses local
`pdf-inspector` extraction when text is available. Scanned or image-based pages,
or a user-selected **Force OCR** path, are rendered by `pypdfium2` and sent to
the configured local Ollama model.

When Ollama is unavailable, native text remains usable. For a scanned page with
no native text, the app shows a warning rather than inventing content.

## Stage 5: Make a safe extension

1. Define expected and actual values, delta convention, and tolerance.
2. Add a focused test using fixtures or a fake OpenAI-compatible client.
3. Implement the calculation in `src/checks.py`; do not import an LLM client.
4. Include failed rows in `failing_row_indices` when appropriate.
5. Confirm retries receive evidence and Python re-runs every check.
6. Update [Checks](CHECKS.md), [Architecture](ARCHITECTURE.md), and the API
   reference if the public result changes.

Use the [Contributor runbook](CONTRIBUTOR_RUNBOOK.md) for validation commands.

## Stage 6: Choose the current APIs

New integrations should use `ingest_document`, `extract_text`, `run_checks`,
and `reconcile_document`. The older tuple-based wrappers support existing code;
see [API reference](API_REFERENCE.md) before using them in new code.
