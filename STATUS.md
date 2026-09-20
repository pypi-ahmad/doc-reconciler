# Status

The Windows-native Streamlit reconciliation pipeline is implemented. Python
determines arithmetic results.

## Documentation

The repository includes onboarding, contributor workflow, a progressive tutorial,
architecture, checks, and supported Python APIs. Source documentation uses
Google-style docstrings and labels compatibility wrappers separately.

## Smoke cache files

These local generated artifacts exist under `data/cache/`:

| File | Evidence |
| --- | --- |
| `last_ingest.json` | Fixture text includes `15.00` and `Total 26.00`. |
| `last_extract.json` | Two amounts (`10.00`, `15.00`) and stated total `26.00`. |
| `last_checks.json` | Deterministic arithmetic check results. |
| `last_reconcile.json` | Full state with extraction, checks, and retry log. |

## Required mismatch

The sum check failed as designed:

```text
check:    items_sum_vs_total
expected: 25.00
actual:   26.00
delta:    -1.00 (expected - actual)
ok:       false
```

The saved reconciliation state contains three retry entries. The final Python
result still has one failed check. The deliberate mismatch remains visible.

## Verified baseline

- `scripts/smoke_ingest.py` wrote `last_ingest.json`.
- `scripts/smoke_extract.py` wrote `last_extract.json`.
- `scripts/smoke_checks.py` confirmed the intended failed sum.
- `scripts/smoke_reconcile.py` wrote `last_reconcile.json` with three retries
  and `final_ok=False`.
- Ruff passed.
- Pytest passed with 7 tests, and the arithmetic docstring doctest passed.
- Public `src/` documentation coverage is 52/52 symbols.

See [Onboarding](docs/ONBOARDING.md) for first use and the
[Contributor runbook](docs/CONTRIBUTOR_RUNBOOK.md) for current commands.
