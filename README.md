# Doc reconciler

> **Python owns the math.**

Doc Reconciler extracts invoice and receipt data with Agnes AI, then validates all calculations in Python. Language models parse document text into Pydantic models, while Python code checks line items, sums, and totals. If an arithmetic check fails, Python calculates the exact difference and sends only the failing rows back to Agnes AI for a targeted correction patch.

## Summary

- Python validates all sums and line-item products without relying on model arithmetic. Never let the model declare a sum correct without `src/checks.py` agreeing.
- Runs on Windows 11 using PowerShell or CMD, without Docker or WSL2.
- Supports multi-page PDF documents via PyMuPDF and text documents via standard text processing.
- Sends Agnes AI (`agnes-3.0-flash`) only the failing rows alongside the calculated numeric error.
- Persists audit trails and reconciliation results to `data/cache/last_reconcile.json`.
- Provides a Streamlit interface across five tabs: Upload, Line items, Checks, Retry log, and Export.

## Deterministic checks

All checks run in [`src/checks.py`](file:///D:/AI/Github/doc-reconciler/src/checks.py) without model calls:

| Check | Logic | Error reported to model |
|---|---|---|
| Sum vs stated total | `round(sum(items.amount), 2) == round(stated_total, 2)` (tolerance slider) | `"sum=25.00 total=26.00 delta=-1.00"` |
| Line item math | `round(qty * unit_price, 2) == round(amount, 2)` | `"row=1 qty=3.0 unit_price=15.00 calculated=45.00 stated=40.00 delta=-5.00"` |
| Duplicate rows | Normalized description and duplicate row detection | `"Duplicate rows detected for description 'managed hosting plan' across rows [0, 3]"` |
| First/last page total mismatch | Compares page 1 total to last page total when both exist | `"page-1 total=140.00 last-page total=230.00 delta=+90.00"` |

## Quick start

### Run with run.cmd
Run [run.cmd](file:///D:/AI/Github/doc-reconciler/run.cmd) directly from Windows Explorer or CMD:
- Creates `.venv` using `py -3` if missing.
- Installs dependencies from [`requirements.txt`](file:///D:/AI/Github/doc-reconciler/requirements.txt).
- If `.env` is missing, copies [`.env.example`](file:///D:/AI/Github/doc-reconciler/.env.example) and opens Notepad.
- Starts Streamlit on `http://localhost:8501`.

### Run with uv
```powershell
uv sync
uv run streamlit run app.py
```

## Configuration and environment

Set the user environment variable `AGNESAI_API_KEY`.
- Base URL default: `https://apihub.agnes-ai.com/v1`
- Model default: `agnes-3.0-flash`
- Optional providers (`OPENAI_API_KEY`, `GOOGLE_API_KEY`) appear in the sidebar dropdown when their environment variables are present.
- API keys are read from environment variables and are not written to source files, logs, or repository history.

## Tests and verification

Run the smoke test suites:

```powershell
# Smoke full loop against Agnes AI and verify data/cache/last_reconcile.json
uv run python tests/smoke_full_loop.py

# Complete unit, model, and check suite
uv run python tests/smoke_test.py
```

Both tests verify that errors in deliberate mismatch fixtures ([`data/fixtures/invoice_mismatch.txt`](file:///D:/AI/Github/doc-reconciler/data/fixtures/invoice_mismatch.txt) and [`data/fixtures/invoice_mismatch.pdf`](file:///D:/AI/Github/doc-reconciler/data/fixtures/invoice_mismatch.pdf)) are flagged by Python, sent back to Agnes AI, and recorded in [`data/cache/last_reconcile.json`](file:///D:/AI/Github/doc-reconciler/data/cache/last_reconcile.json).

## Project structure

```
doc-reconciler/
├── app.py                     # Streamlit frontend (Upload, Line items, Checks, Retry log, Export)
├── run.cmd                    # Windows 11 launcher
├── requirements.txt           # streamlit, openai, python-dotenv, pymupdf, pydantic, pandas, pillow
├── pyproject.toml             # Python project configuration
├── STATUS.md                  # Execution and verification log
├── data/
│   ├── cache/                 # Reconciliation audit cache (last_reconcile.json)
│   └── fixtures/              # Deliberate mismatch fixtures (invoice_mismatch.txt, invoice_mismatch.pdf)
├── docs/
│   └── ARCHITECTURE.md        # Loop diagram and architecture
├── src/
│   ├── agnes_client.py        # Agnes AI client configuration
│   ├── checks.py              # Deterministic Python checks (no LLM, returns list[CheckResult])
│   ├── extract.py             # Agnes JSON extraction and page merger (list[LineItem] + totals)
│   ├── models.py              # Pydantic schemas (LineItem, DocumentTotal, CheckResult)
│   ├── pdf_processor.py       # PyMuPDF multi-page parser and image renderer
│   ├── providers.py           # Multi-provider detection helper
│   └── retry.py               # Option B feedback loop with JSON patches (max 3 retries)
└── tests/
    ├── smoke_full_loop.py     # Live Agnes loop validation saving last_reconcile.json
    ├── smoke_test.py          # Fast unit and integration tests
    └── test_extract_and_retry.py # Multi-page PDF live test
```
