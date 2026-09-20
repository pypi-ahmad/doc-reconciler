"""Live Agnes extraction smoke using the cached ingest text."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.extract import extract_text


def main() -> None:
    ingest_cache = REPO_ROOT / "data" / "cache" / "last_ingest.json"
    extract_cache = REPO_ROOT / "data" / "cache" / "last_extract.json"
    ingest = json.loads(ingest_cache.read_text(encoding="utf-8"))
    extraction = extract_text(str(ingest["text"]))

    amounts = sorted(item.amount for item in extraction.items if item.amount is not None)
    assert amounts == [10.0, 15.0], f"Expected line amounts [10.0, 15.0], got {amounts}"
    assert extraction.totals.total == 26.0, (
        f"Expected stated total 26.0, got {extraction.totals.total}"
    )

    extract_cache.parent.mkdir(parents=True, exist_ok=True)
    extract_cache.write_text(extraction.model_dump_json(indent=2), encoding="utf-8")
    print(f"Extraction smoke passed: {extract_cache}")


if __name__ == "__main__":
    main()
