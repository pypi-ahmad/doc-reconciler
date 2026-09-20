# Document Reconciler

Document Reconciler is a Windows-native Streamlit app for extracting invoice-like
documents and checking their arithmetic. Python owns the math: Agnes extracts
values and may propose a patch, but it never declares a sum correct.

## Documentation

| Goal | Start here |
| --- | --- |
| Run the app for the first time | [Onboarding](docs/ONBOARDING.md) |
| Change and verify the repository | [Contributor runbook](docs/CONTRIBUTOR_RUNBOOK.md) |
| Learn the system progressively | [Zero to mastery](docs/ZERO_TO_MASTERY.md) |
| Use the Python interfaces | [API reference](docs/API_REFERENCE.md) |
| Understand the pipeline | [Architecture](docs/ARCHITECTURE.md) |
| Look up arithmetic rules | [Checks](docs/CHECKS.md) |
| Review saved smoke evidence | [Status](STATUS.md) |

## Processing

1. Text files are read directly. PDFs are classified and processed locally by
   `pdf-inspector`; this project does not use Firecrawl Cloud.
2. Native PDF text is preferred. Ollama OCR runs only when a document is routed
   to OCR or **Force OCR** is selected.
3. `agnes-3.0-flash` extracts line items and stated totals through the official
   OpenAI SDK using `AGNESAI_API_KEY` from the Windows user environment.
4. Python applies deterministic checks and, on failure, can request up to three
   narrowly scoped Agnes patches. Python rechecks every patch.

## Fixture with a known mismatch

`data/fixtures/invoice_mismatch.txt` contains two valid amounts but a total
that is wrong by `1.00`.

```text
10.00 + 15.00 = 25.00
stated total  = 26.00
delta         = -1.00  (expected - actual)
```

The fixture is intentionally wrong by `1.00`. Smoke output should report the
sum check as failed; it must not be hidden as a pass.

## Run on Windows 11

Set `AGNESAI_API_KEY` as a Windows user environment variable, then run:

```bat
run.cmd
```

On the first run, `run.cmd` creates `.env` from `.env.example`, opens it in
Notepad, then exits. Leave secrets out of that file: the app reads the process
environment, not `.env`. Close Notepad, open a terminal that can see your user
environment variable, and run `run.cmd` again.

The app has Health, Upload, Line items, Checks, Retry log, and Export pages.
Health shows availability only and never reveals secret values.

`run.cmd` closes any process listening on port `8593` before starting the app at
`http://localhost:8593`.
