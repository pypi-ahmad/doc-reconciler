# Contributor Runbook

Use this runbook for local changes to Document Reconciler. It covers the
repository's verified workflow and leaves branch, pull-request, release, and
deployment choices to the surrounding project process.

## Local setup

Start the app with [run.cmd](../run.cmd). For the development tools declared in
`pyproject.toml`, synchronize the development group:

```powershell
uv sync --group dev
```

The launcher starts Streamlit at `http://localhost:8593`. Before it starts, it
closes any existing process listening on port `8593`.

Run checks from the repository root:

```powershell
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pytest --doctest-modules src
```

## Source map

| Area | Primary module | Invariant |
| --- | --- | --- |
| Settings | `src/config.py` | Secrets come from the process environment. |
| Ingestion | `src/ingest.py` | `.txt` stays native; PDFs return route, type, text, and pages. |
| PDF and OCR | `src/pdf_processor.py` | Local `pdf-inspector`; Ollama only when routed or forced. |
| Extraction | `src/extract.py` | Preserve stated values; do not repair arithmetic. |
| Checks | `src/checks.py` | Python owns arithmetic and imports no LLM client. |
| Retry | `src/retry.py` | Send failure evidence and exact delta; re-run Python checks. |
| UI | `app.py` | Show route, checks, retries, and export without exposing secrets. |

## Change workflow

1. Identify the smallest owning module from the source map.
2. Add or update a focused test before changing a contract.
3. Use models for extraction and patches. Keep arithmetic in `src/checks.py`.
4. Run Ruff and Pytest. Run relevant smoke scripts when prerequisites exist.
5. Update the matching reference, tutorial, or architecture document.

## Smoke scripts and cache order

- `.venv\Scripts\python scripts\smoke_ingest.py` is offline and writes
  `last_ingest.json` from the fixture.
- `.venv\Scripts\python scripts\smoke_extract.py` needs the ingest cache and
  Agnes key, then writes `last_extract.json`.
- `.venv\Scripts\python scripts\smoke_checks.py` is offline, needs the extract
  cache, and writes `last_checks.json`.
- `.venv\Scripts\python scripts\smoke_reconcile.py` needs the fixture and Agnes
  key, then writes `last_reconcile.json`.

All files are written under `data/cache/`. They are ignored local artifacts;
do not use them as a substitute for tests.

## Troubleshooting

- **Button disabled:** If Health reports a missing key, set `AGNESAI_API_KEY` in
  the user environment and open a new terminal.
- **OCR lacks useful text:** If Health reports Ollama unavailable, start Ollama,
  use native text, or use a `.txt` fixture.
- **Missing extraction cache:** Run `smoke_ingest.py`, then `smoke_extract.py`.
- **Arithmetic passes unexpectedly:** Inspect amounts and total, repair
  extraction evidence if needed, then rerun checks.
- **Agnes is throttled:** The client retries with bounded backoff; retry later
  if its final attempt is exhausted.

## Definition of done

Before handing off a local change, confirm that relevant tests pass and docs
match behavior. Do not print or write secrets. Keep discrepancies visible until
the deterministic Python checks pass.
