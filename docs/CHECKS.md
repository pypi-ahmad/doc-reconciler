# Arithmetic Checks

All checks run in `src/checks.py` without an LLM import. Values are converted to
`Decimal`, rounded to cents with `ROUND_HALF_UP`, and compared with the selected
tolerance. The default tolerance is `0.01`.

```text
delta = expected - actual
pass  = abs(delta) <= tolerance
```

## Formulas

| Check | Expected | Actual | Failure behavior |
| --- | --- | --- | --- |
| `items_sum_vs_total` | Sum of amounts | Stated total | Missing input fails. |
| `qty_times_unit_vs_amount` | `qty * unit_price` | Row amount | Missing input fails. |
| `duplicate_desc` | Unique descriptions | Repeated descriptions | Repeated non-empty values fail. |
| `first_vs_last_total` | First page total | Last page total | Requires two page totals. |

Descriptions are normalized with `strip()` and case folding. Failed numeric
checks include the exact delta; failed row checks are added to retry context.

## Fixture example

The required fixture contains two correct rows and one deliberately incorrect
printed total:

```text
expected = 10.00 + 15.00 = 25.00
actual   = 26.00
delta    = 25.00 - 26.00 = -1.00
result   = failed
```

The negative sign means the stated total exceeds the item sum. Its absolute
discrepancy, `1.00`, exceeds the default tolerance and must remain visible.

## Related documentation

- [Architecture](ARCHITECTURE.md)
- [Zero to mastery](ZERO_TO_MASTERY.md)
- [API reference](API_REFERENCE.md)
