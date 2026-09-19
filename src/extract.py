"""Extract line items and totals per page using Agnes AI, then merge across pages."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from openai import OpenAI

from src.models import DocumentTotal, LineItem
from src.agnes_client import DEFAULT_AGNES_MODEL, get_agnes_client, get_available_providers, get_provider_client


def clean_json_text(text: str) -> str:
    """Strip markdown code fence blocks if present."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def extract_page_line_items(
    page_text: str,
    page_num: int,
    client: OpenAI,
    model: str = DEFAULT_AGNES_MODEL,
) -> Tuple[List[LineItem], Optional[float], Dict[str, Any]]:
    """Extract line items and page totals for a single page via Agnes Chat Completions.

    Returns (line_items, page_stated_total, raw_totals_dict).
    """
    if not page_text.strip():
        return [], None, {}

    system_prompt = (
        "You are an expert financial document data extractor. Extract line items and document totals "
        "accurately from the provided page text into strict JSON format.\n"
        "Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "line_items": [\n'
        "    {\n"
        '      "description": "Item description or name",\n'
        '      "qty": 1.0,\n'
        '      "unit_price": 25.0,\n'
        '      "amount": 25.0,\n'
        '      "raw": "Exact raw text line from page for this item"\n'
        "    }\n"
        "  ],\n"
        '  "page_total": 25.0,\n'
        '  "subtotal": 25.0,\n'
        '  "tax": 0.0,\n'
        '  "shipping": 0.0,\n'
        '  "discount": 0.0,\n'
        '  "grand_total": 25.0,\n'
        '  "currency": "USD"\n'
        "}\n"
        "Notes:\n"
        "- If page_total, tax, or other totals are not present on this page, set them to null.\n"
        "- Do not fabricate figures. Extract exact numbers stated in the text."
    )

    user_prompt = f"Page {page_num} Text Content:\n\n{page_text}"

    response = None
    for attempt in range(4):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
            )
            break
        except Exception as e:
            if "rate limit" in str(e).lower() and attempt < 3:
                time.sleep((attempt + 1) * 3)
                continue
            raise

    content = response.choices[0].message.content or "{}" if response else "{}"
    cleaned = clean_json_text(content)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = {"line_items": []}

    raw_items = data.get("line_items", [])
    parsed_items: List[LineItem] = []
    for item in raw_items:
        try:
            qty = float(item["qty"]) if item.get("qty") is not None else None
        except (ValueError, TypeError):
            qty = None
        try:
            unit_price = float(item["unit_price"]) if item.get("unit_price") is not None else None
        except (ValueError, TypeError):
            unit_price = None
        try:
            amount = float(item["amount"]) if item.get("amount") is not None else None
        except (ValueError, TypeError):
            amount = None

        desc = str(item.get("description", "")).strip()
        raw = str(item.get("raw", "")).strip()

        parsed_items.append(
            LineItem(
                qty=qty,
                unit_price=unit_price,
                amount=amount,
                page=page_num,
                raw=raw,
                description=desc,
            )
        )

    # Page total
    page_tot = None
    if data.get("page_total") is not None:
        try:
            page_tot = float(data["page_total"])
        except (ValueError, TypeError):
            page_tot = None
    elif data.get("grand_total") is not None:
        try:
            page_tot = float(data["grand_total"])
        except (ValueError, TypeError):
            page_tot = None
    elif data.get("subtotal") is not None:
        try:
            page_tot = float(data["subtotal"])
        except (ValueError, TypeError):
            page_tot = None

    totals_dict = {
        "subtotal": data.get("subtotal"),
        "tax": data.get("tax"),
        "shipping": data.get("shipping"),
        "discount": data.get("discount"),
        "grand_total": data.get("grand_total"),
        "currency": data.get("currency", "USD"),
        "page_total": page_tot,
    }

    return parsed_items, page_tot, totals_dict


def extract_and_merge_document(
    pages: List[Dict[str, Any]],
    client: Optional[OpenAI] = None,
    model: str = DEFAULT_AGNES_MODEL,
) -> Tuple[DocumentTotal, List[LineItem]]:
    """Extract line items per page and merge across all pages of the document."""
    if client is None:
        client = get_agnes_client()

    all_line_items: List[LineItem] = []
    page_totals: Dict[int, float] = {}
    last_totals_dict: Dict[str, Any] = {}

    for i, page_info in enumerate(pages):
        p_num = page_info.get("page", i + 1)
        p_text = page_info.get("text", "")

        # Small pause between pages to respect free tier rate limit
        if i > 0:
            time.sleep(1.0)

        items, p_total, totals_dict = extract_page_line_items(
            page_text=p_text,
            page_num=p_num,
            client=client,
            model=model,
        )

        all_line_items.extend(items)
        if p_total is not None:
            page_totals[p_num] = p_total

        # Save last non-empty totals dict
        if any(totals_dict.get(k) is not None for k in ["subtotal", "grand_total", "tax", "total"]):
            last_totals_dict = totals_dict

    # Build DocumentTotal
    grand_total = None
    subtotal = None
    tax = None
    shipping = None
    discount = None
    currency = "USD"

    if last_totals_dict:
        try:
            grand_total = float(last_totals_dict.get("grand_total") or last_totals_dict.get("total") or 0.0)
        except (ValueError, TypeError):
            grand_total = None
        try:
            subtotal = float(last_totals_dict.get("subtotal") or 0.0)
        except (ValueError, TypeError):
            subtotal = None
        try:
            tax = float(last_totals_dict.get("tax") or 0.0)
        except (ValueError, TypeError):
            tax = None
        try:
            shipping = float(last_totals_dict.get("shipping") or 0.0)
        except (ValueError, TypeError):
            shipping = None
        try:
            discount = float(last_totals_dict.get("discount") or 0.0)
        except (ValueError, TypeError):
            discount = None
        currency = last_totals_dict.get("currency", "USD") or "USD"

    doc_total = DocumentTotal(
        subtotal=subtotal,
        tax=tax,
        shipping=shipping,
        discount=discount,
        total=grand_total if grand_total is not None else subtotal,
        currency=currency,
        page=len(pages),
        page_totals=page_totals,
        raw=json.dumps(last_totals_dict),
    )

    return doc_total, all_line_items


def extract_from_text(
    raw_text: str,
    client: Optional[OpenAI] = None,
    model: str = DEFAULT_AGNES_MODEL,
) -> Tuple[DocumentTotal, List[LineItem]]:
    """Extract line items and stated totals from plain text invoice/stand-in."""
    # Split by standard page breaks or treat as single page
    pages_raw = re.split(r"(?:---+\s*Page\s*\d+\s*---+|\f)", raw_text)
    pages = [
        {"page": idx + 1, "text": chunk.strip()}
        for idx, chunk in enumerate(pages_raw)
        if chunk.strip()
    ]
    if not pages:
        pages = [{"page": 1, "text": raw_text.strip()}]

    return extract_and_merge_document(pages=pages, client=client, model=model)
