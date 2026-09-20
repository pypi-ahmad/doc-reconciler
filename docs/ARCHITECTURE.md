# Architecture

Document Reconciler is a Windows-native Streamlit pipeline. Models extract and
propose patches; deterministic Python decides whether the document reconciles.

## Processing flow

```text
Upload .txt or PDF
        |
        v
Ingest and route
  .txt --------------------------> native text
  PDF -> local pdf-inspector ----> native text when available
              |
              +------------------> pypdfium2 PNGs -> Ollama OCR when routed
        |
        v
Agnes extraction: {items, totals, notes}
        |
        v
Python checks <----------------------------------------------+
        |                                                    |
        +-- all pass ----------------------> ReconcileState/export
        |                                                    |
        +-- any fail                                        |
                |                                            |
                v                                            |
        Send failing rows, totals, and exact numeric delta   |
        to Agnes for {items?, totals?} JSON patch             |
                |                                            |
                v                                            |
        Merge patch -----------------------------------------+
                |
                +-- stop after all checks pass or 3 attempts
```

## Component ownership

| Component | Owns | Does not own |
| --- | --- | --- |
| `src/ingest.py` | Source handling and normalized page text | Agnes extraction |
| `src/pdf_processor.py` | Local PDF classification, rendering, OCR routing | Cloud parsing |
| `src/extract.py` | Schema-constrained stated-value extraction | Arithmetic approval |
| `src/checks.py` | Decimal arithmetic and validation | LLM requests |
| `src/retry.py` | Bounded patch requests and state merge | Pass/fail authority |
| `src/pipeline.py` | End-to-end orchestration | UI rendering |
| `app.py` | Streamlit interaction and JSON export | Secret display |

## Retry contract

Every retry receives only the current failing rows, stated totals, and a message
in this form:

```text
sum(items)=X stated_total=Y delta=Z
```

Agnes may return an `items` patch, a `totals` patch, or both. Python merges the
patch and runs all checks again. Each attempt records failed checks, sent rows,
the patch, post-patch checks, and a truncated raw source snippet. The loop stops
when every check passes or the configured maximum reaches three attempts.

An unresolved discrepancy stays failed in the returned state. The model cannot
override or convert a Python failure into a passing result.

## Secrets and services

The Agnes client reads `AGNESAI_API_KEY` from the process environment and never
writes it to files or logs. `AGNES_BASE_URL` is named in `.env.example` by the
project contract, while the runtime client uses the fixed Agnes endpoint.

Ollama is optional and used only for OCR-routed pages or Force OCR. When it is
unavailable, native text remains usable; a scanned page without native text
returns a warning instead of invented content.

## Related documentation

- [Onboarding](ONBOARDING.md)
- [Contributor runbook](CONTRIBUTOR_RUNBOOK.md)
- [Zero to mastery](ZERO_TO_MASTERY.md)
- [API reference](API_REFERENCE.md)
- [Checks](CHECKS.md)
