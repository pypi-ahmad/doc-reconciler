"""Strict Agnes extraction into Pydantic invoice models."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from src.agnes_client import DEFAULT_AGNES_MODEL, create_chat_completion
from src.models import DocumentTotal, ExtractionResult, LineItem

EXTRACTION_PROMPT = """Extract only values explicitly stated in the supplied invoice text.
Return exactly one JSON object with this schema:
{
  "items": [
    {
      "sku": null,
      "desc": "Line description",
      "qty": 1,
      "unit_price": 10.00,
      "amount": 10.00,
      "page": 1,
      "raw": "exact source line"
    }
  ],
  "totals": {"subtotal": null, "tax": null, "total": 26.00, "page": 1},
  "notes": ""
}
Use JSON numbers without currency symbols. Use null when a value is absent.
Preserve stated values even when their arithmetic appears wrong. Never invent or correct values.
Return JSON only. No Markdown fences, commentary, or extra keys."""


def clean_json_text(text: str) -> str:
    """Extract the first valid JSON object from plain or fenced model output.

    Args:
        text: Raw Agnes response content.

    Returns:
        A serialized JSON object without surrounding prose or Markdown fences.

    Raises:
        ValueError: If no valid JSON object occurs in the response.
    """
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, re.IGNORECASE)
    candidate = fenced.group(1).strip() if fenced else stripped
    decoder = json.JSONDecoder()
    for index, character in enumerate(candidate):
        if character != "{":
            continue
        try:
            value, _end = decoder.raw_decode(candidate[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return json.dumps(value)
    raise ValueError("Agnes response did not contain a valid JSON object.")


def _decimal_float(value: Any, *, field: str) -> float | None:
    """Coerce a JSON number or currency-like string through Decimal first."""
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "null", "none"}):
        return None
    if isinstance(value, bool):
        raise TypeError(f"{field} must be numeric, not boolean.")
    cleaned = str(value).strip().replace(",", "")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    cleaned = re.sub(r"^[^\d+\-.]+|[^\d]+$", "", cleaned)
    try:
        number = Decimal(cleaned)
    except InvalidOperation as error:
        raise ValueError(f"{field} is not a valid number.") from error
    if not number.is_finite():
        raise ValueError(f"{field} must be finite.")
    return float(-number if negative else number)


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize common model variations into the required schema."""
    raw_items = payload.get("items", payload.get("line_items"))
    if not isinstance(raw_items, list):
        raise TypeError("Agnes extraction schema requires an items array.")

    items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise TypeError(f"items[{index}] must be an object.")
        item = dict(raw_item)
        item["desc"] = item.get("desc", item.get("description"))
        item["qty"] = _decimal_float(item.get("qty"), field=f"items[{index}].qty")
        item["unit_price"] = _decimal_float(
            item.get("unit_price", item.get("unit")),
            field=f"items[{index}].unit_price",
        )
        item["amount"] = _decimal_float(item.get("amount"), field=f"items[{index}].amount")
        item["page"] = int(_decimal_float(item.get("page", 1), field=f"items[{index}].page") or 1)
        item["raw"] = str(item.get("raw") or "")
        items.append(item)

    raw_totals = payload.get("totals")
    if not isinstance(raw_totals, dict):
        raw_totals = {
            "subtotal": payload.get("subtotal"),
            "tax": payload.get("tax"),
            "total": payload.get("total", payload.get("grand_total", payload.get("page_total"))),
            "page": payload.get("page", 1),
        }
    totals = {
        name: _decimal_float(raw_totals.get(name), field=f"totals.{name}")
        for name in ("subtotal", "tax", "total")
    }
    totals["page"] = int(_decimal_float(raw_totals.get("page", 1), field="totals.page") or 1)
    return {"items": items, "totals": totals, "notes": str(payload.get("notes") or "")}


def parse_extraction(content: str) -> ExtractionResult:
    """Parse, normalize, and validate one Agnes response.

    Args:
        content: Raw JSON-only response or a response containing a JSON fence.

    Returns:
        Extraction result with Decimal-safe numeric coercion applied.

    Raises:
        ValueError: If JSON, numeric values, or schema validation are invalid.
        TypeError: If the payload object or its required items array is invalid.
    """
    try:
        payload = json.loads(clean_json_text(content))
    except json.JSONDecodeError as error:
        raise ValueError("Agnes response contained malformed JSON.") from error
    if not isinstance(payload, dict):
        raise TypeError("Agnes extraction response must be a JSON object.")
    try:
        return ExtractionResult.model_validate(_normalize_payload(payload))
    except ValidationError as error:
        raise ValueError(f"Agnes extraction schema validation failed: {error}") from error


def extract_text(
    text: str,
    *,
    client: OpenAI | None = None,
    model: str = DEFAULT_AGNES_MODEL,
) -> ExtractionResult:
    """Call Agnes at temperature zero and return a validated extraction.

    Args:
        text: Concatenated source document text.
        client: Optional Agnes-compatible client, useful for offline tests.
        model: Agnes model identifier.

    Returns:
        Validated line items, stated totals, and extraction notes.

    Raises:
        ValueError: If text is empty or the provider response is malformed.
    """
    if not text.strip():
        raise ValueError("Document text is empty.")
    response = create_chat_completion(
        [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": f"Invoice text:\n\n{text}"},
        ],
        client=client,
        model=model,
    )
    return parse_extraction(response.choices[0].message.content or "")


def _legacy_result(result: ExtractionResult) -> tuple[DocumentTotal, list[LineItem]]:
    totals = result.totals
    return (
        DocumentTotal(
            subtotal=totals.subtotal,
            tax=totals.tax,
            total=totals.total,
            page=totals.page,
        ),
        result.items,
    )


def extract_from_text(
    raw_text: str,
    client: OpenAI | None = None,
    model: str = DEFAULT_AGNES_MODEL,
) -> tuple[DocumentTotal, list[LineItem]]:
    """Return the compatibility tuple form of one text extraction.

    Args:
        raw_text: Source document text.
        client: Optional Agnes-compatible client.
        model: Agnes model identifier.

    Returns:
        The older ``(DocumentTotal, list[LineItem])`` contract.

    Raises:
        ValueError: If the source or provider response is invalid.
    """
    return _legacy_result(extract_text(raw_text, client=client, model=model))


def extract_and_merge_document(
    pages: list[dict[str, Any]],
    client: OpenAI | None = None,
    model: str = DEFAULT_AGNES_MODEL,
) -> tuple[DocumentTotal, list[LineItem]]:
    """Extract page dictionaries through the compatibility tuple interface.

    Args:
        pages: Dictionaries containing page numbers and text values.
        client: Optional Agnes-compatible client.
        model: Agnes model identifier.

    Returns:
        The older document-total and line-item tuple.

    Raises:
        ValueError: If merged text or provider output is invalid.
    """
    text = "\n\n".join(
        f"--- Page {page.get('page', index + 1)} ---\n{page.get('text', '')}"
        for index, page in enumerate(pages)
    )
    return _legacy_result(extract_text(text, client=client, model=model))


def extract_page_line_items(
    page_text: str,
    page_num: int,
    client: OpenAI,
    model: str = DEFAULT_AGNES_MODEL,
) -> tuple[list[LineItem], float | None, dict[str, Any]]:
    """Extract one page through the compatibility return contract.

    Args:
        page_text: Text extracted from one page.
        page_num: One-based page number to assign to extracted items.
        client: Agnes-compatible client.
        model: Agnes model identifier.

    Returns:
        Extracted items, the stated page total, and serialized totals.

    Raises:
        ValueError: If page text or provider output is invalid.
    """
    result = extract_text(page_text, client=client, model=model)
    for item in result.items:
        item.page = page_num
    totals = result.totals.model_dump()
    return result.items, result.totals.total, totals
