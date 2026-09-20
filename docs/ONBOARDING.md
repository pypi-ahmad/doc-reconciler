# Onboarding

Use this guide to move from an existing Windows checkout to a verified local
run. It assumes basic Python and PowerShell familiarity.

## 1. Confirm prerequisites

Use Windows 11 with the Python launcher available:

```powershell
py -3 --version
```

The full reconciliation flow also needs `AGNESAI_API_KEY` in the Windows user
environment. Verify presence without printing its value:

```powershell
if ($env:AGNESAI_API_KEY) { "AGNESAI_API_KEY is set" } else { "AGNESAI_API_KEY is missing" }
```

Open a new terminal after adding a user environment variable. Ollama is not
needed for the text fixture or text-based PDFs; it is used only on the OCR
route.

## 2. Start the application

From the repository root, run:

```bat
run.cmd
```

The first invocation creates `.env` from `.env.example`, opens Notepad, and
exits. Do not put the Agnes key in `.env`; close Notepad and run `run.cmd`
again. The launcher creates `.venv`, installs `requirements.txt`, and starts
Streamlit at `http://localhost:8593`. It closes any existing listener on port
`8593` before starting the app.

## 3. Upload the fixture

In the app:

1. Open **Health** and confirm the key status. This check makes no Agnes call.
2. Open **Upload** and select `data/fixtures/invoice_mismatch.txt`.
3. Confirm the route is `native` and the preview contains `Total 26.00`.
4. Open **Line items** and choose **Run full reconciliation** when enabled.
5. Inspect **Checks** and **Retry log**. The fixture should retain a failed
   `items_sum_vs_total` result unless extraction finds different source values.

The expected fixture arithmetic is documented in [Checks](CHECKS.md).

## 4. Run the first offline smoke

With the virtual environment created, run the ingestion smoke:

```powershell
.venv\Scripts\python scripts\smoke_ingest.py
```

It writes `data/cache/last_ingest.json` and checks for both `15.00` and
`Total 26.00`. The cache directory contains local evidence, not source data to
commit.

## Next steps

- Follow the [Contributor runbook](CONTRIBUTOR_RUNBOOK.md) before changing
  source files.
- Follow [Zero to mastery](ZERO_TO_MASTERY.md) to trace the pipeline.
- Use the [API reference](API_REFERENCE.md) for Python integrations.
