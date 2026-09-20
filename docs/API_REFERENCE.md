# Python API Reference

Use the active pipeline APIs for new work. The compatibility interfaces support
existing callers and are listed separately below.

## Active pipeline

### Ingestion

```python
ingest_document(
    source: str | os.PathLike[str] | bytes,
    *,
    filename: str | None = None,
    force_ocr: bool = False,
) -> IngestResult
```

`ingest_document` accepts `.txt` and `.pdf` sources. It returns an
`IngestResult` with `route`, `pdf_type`, combined `text`, and numbered `pages`.
It raises `ValueError` for unsupported extensions and can surface filesystem,
PDF, or OCR failures.

### Extraction

```python
extract_text(text: str, *, client: OpenAI | None = None, model: str = DEFAULT_AGNES_MODEL)
    -> ExtractionResult
```

`extract_text` requests JSON-only extraction at temperature zero. It requires
non-empty text and returns Pydantic `items`, stated `totals`, and `notes`.
Malformed JSON, schema values, and provider errors propagate as exceptions; the
function does not correct arithmetic.

### Deterministic checks

```python
run_checks(
    doc_total: DocumentTotal,
    line_items: list[LineItem],
    tolerance: float = 0.01,
    page_totals: dict[int, float] | None = None,
) -> ReconciliationResult
```

The result contains individual `CheckResult` values, `is_valid`, failed row
indices, exact numeric errors, and discrepancies. Delta is `expected - actual`.

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

assert result.is_valid is False
```

### End-to-end reconciliation

```python
reconcile_document(
    source: str | os.PathLike[str] | bytes,
    *,
    filename: str | None = None,
    force_ocr: bool = False,
    tolerance: float = 0.01,
    max_retries: int = 3,
    client: OpenAI | None = None,
    model: str = DEFAULT_AGNES_MODEL,
) -> ReconcileState
```

`reconcile_document` ingests, extracts, checks, and retries in sequence.
`max_retries` is clamped to three. It returns `ReconcileState` when checks still
fail, so inspect `state.checks` and `state.retries` after each run.

`reconcile_ingest` provides the same flow for an existing `IngestResult`.
`retry_failed_checks` accepts an existing `ReconcileState` and uses the same
bounded retry behavior.

## Models and configuration

| Type | Purpose |
| --- | --- |
| `LineItem` | Extracted SKU, description, quantity, unit price, amount, page, and raw text. |
| `DocumentTotals` | Stated subtotal, tax, total, and source page in the active pipeline. |
| `ExtractionResult` | Agnes payload: `items`, `totals`, and `notes`. |
| `CheckResult` | One deterministic result with expected, actual, delta, and detail. |
| `ReconcileState` | Session-safe items, totals, checks, retry records, and page text. |
| `Settings` | Process-environment configuration for Agnes and Ollama. |

Use `get_settings()` to read configuration without logging secrets. Use
`get_agnes_client()` to create the fixed Agnes client; it raises `ValueError`
when `AGNESAI_API_KEY` is unavailable.

## PDF and Ollama helpers

`PDFDocument` classifies a PDF with local `pdf-inspector`, exposes rendered
pages, and cleans up temporary byte-backed files when closed. Prefer its context
manager form. `build_ocr_prompt()` creates the OCR and optional table
recognition instruction. `is_ollama_available()` returns `(available, status)`;
`extract_tables_with_ollama()` returns Markdown or raises for unavailable images
or services.

## Compatibility interfaces

| Interface | Compatibility behavior |
| --- | --- |
| `extract_from_text` | Returns `(DocumentTotal, list[LineItem])`. |
| `extract_and_merge_document` | Accepts page dictionaries and returns the older tuple. |
| `extract_page_line_items` | Returns one page's items, total, and totals dictionary. |
| `retry_reconciliation_loop` | Adapts active state retries to the older tuple-and-log result. |
| `run_deterministic_checks` | Delegates to `run_checks` with the older result type. |
| `providers.ModelOption` and `get_openai_client` | Aliases for the fixed Agnes provider. |
| `ReconciliationCheck` | Alias for `CheckResult`. |

`DocumentTotal`, `ReconciliationResult`, and `RetryLogEntry` remain useful at
check and compatibility boundaries. Source docstrings describe their fields and
exception behavior.
