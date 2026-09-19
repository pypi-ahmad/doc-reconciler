# Implementation status

## Overview
Doc Reconciler is implemented and verified on Windows 11. Agnes AI handles document extraction and targeted JSON patches, while Python code runs all mathematical checks and calculates error deltas. Python owns the math.

## Test execution and verification

### Environment and setup
- OS: Native Windows 11 (PowerShell / CMD), without Docker or WSL2.
- Python: 3.14.7 managed via `uv` in `.venv`.
- Launcher: `run.cmd` verified for `.venv` setup, dependency installation, and `.env.example` copy behavior.
- Dependencies: Streamlit, PyMuPDF, Pydantic, Pandas, OpenAI SDK, python-dotenv, Pillow. No Qdrant.

### Smoke full loop against Agnes AI
- Command: `uv run python tests/smoke_full_loop.py`
- Result: Passed (exit code 0).
  - Loaded deliberate mismatch fixture [`data/fixtures/invoice_mismatch.txt`](file:///D:/AI/Github/doc-reconciler/data/fixtures/invoice_mismatch.txt) (items $10.00 + $15.00 = $25.00 vs printed total $26.00).
  - Agnes AI (`agnes-3.0-flash`) extracted line items and totals via [`src/extract.py`](file:///D:/AI/Github/doc-reconciler/src/extract.py).
  - Deterministic checks in [`src/checks.py`](file:///D:/AI/Github/doc-reconciler/src/checks.py) identified the mismatch: `sum=25.00 total=26.00 delta=-1.00`.
  - Retry loop in [`src/retry.py`](file:///D:/AI/Github/doc-reconciler/src/retry.py) sent only failing rows and the numeric discrepancy to Agnes.
  - Agnes returned a JSON patch correcting total to $25.00. Python re-evaluated and validated the patch.
  - Audit state was persisted to [`data/cache/last_reconcile.json`](file:///D:/AI/Github/doc-reconciler/data/cache/last_reconcile.json), verifying at least one failed check and one retry entry.

### Unit, models, and checks suite
- Command: `uv run python tests/smoke_test.py`
- Result: Passed (exit code 0).
  - Validated Pydantic models: [`LineItem`](file:///D:/AI/Github/doc-reconciler/src/models.py#L10), [`DocumentTotal`](file:///D:/AI/Github/doc-reconciler/src/models.py#L22), [`CheckResult`](file:///D:/AI/Github/doc-reconciler/src/models.py#L38).
  - Verified 4 deterministic checks without model calls: `sum(items) == total`, `qty * price == amount`, duplicate rows, first/last page total mismatch.
  - Verified PyMuPDF multi-page rendering and text extraction.
  - Verified safe provider detection without exposing secrets.

### Streamlit application
- Command: `uv run python -c "import app; print('app imports verified')"`
- Result: Passed (exit code 0).
- Interface includes five tabs:
  1. Upload: Multi-page preview, image rendering, text document view, extraction trigger.
  2. Line items: Table of extracted items, raw snippets, and totals.
  3. Checks: Deterministic check table, numeric error displays, tolerance slider, retry button.
  4. Retry log: Audit records showing failing rows sent, error strings, and returned patches.
  5. Export: Downloads for CSV, JSON payload, and Markdown reports.

### Documentation
- [README.md](file:///D:/AI/Github/doc-reconciler/README.md): Documents the architecture, quickstart, and configuration.
- [docs/ARCHITECTURE.md](file:///D:/AI/Github/doc-reconciler/docs/ARCHITECTURE.md): Contains the loop diagram and component breakdown.

## Remaining risks and mitigations
- Network latency: Extraction queries Agnes per page. Documents with more than ten pages will benefit from batched or asynchronous requests.
- Image-only PDFs: PyMuPDF extracts embedded text directly. Scanned documents without a text layer require an OCR pre-processing step.
