"""Offline ingestion smoke for the deliberate mismatch text fixture."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.ingest import ingest_document


def main() -> None:
    fixture = REPO_ROOT / "data" / "fixtures" / "invoice_mismatch.txt"
    cache = REPO_ROOT / "data" / "cache" / "last_ingest.json"
    result = ingest_document(fixture)

    assert result["route"] == "native"
    assert "15.00" in result["text"]
    assert "Total 26.00" in result["text"]

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Ingest smoke passed: {cache}")


if __name__ == "__main__":
    main()
