"""Pydantic data models for document reconciliation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    """Extracted line item from invoice / receipt / financial document."""

    qty: Optional[float] = Field(default=None, description="Item quantity")
    unit_price: Optional[float] = Field(default=None, description="Item unit price")
    amount: Optional[float] = Field(default=None, description="Total amount for line item")
    page: int = Field(default=1, description="Source page number (1-indexed)")
    raw: str = Field(default="", description="Exact raw text snippet from document")
    description: Optional[str] = Field(default="", description="Description or product name")


class DocumentTotal(BaseModel):
    """Document total figures extracted from document."""

    subtotal: Optional[float] = Field(default=None, description="Subtotal before taxes/discounts")
    tax: Optional[float] = Field(default=None, description="Tax amount")
    shipping: Optional[float] = Field(default=None, description="Shipping or handling fee")
    discount: Optional[float] = Field(default=None, description="Discounts applied")
    total: Optional[float] = Field(default=None, description="Grand total stated on document")
    currency: str = Field(default="USD", description="Currency symbol or 3-letter code")
    page: Optional[int] = Field(default=1, description="Page number where grand total appears")
    page_totals: Dict[int, float] = Field(
        default_factory=dict,
        description="Stated totals per page: {page_num: stated_page_total}",
    )
    raw: str = Field(default="", description="Raw text snippet of totals summary")


class CheckResult(BaseModel):
    """Outcome of a single deterministic mathematical check."""

    name: str = Field(description="Name or category of the check")
    passed: bool = Field(description="Whether the check succeeded")
    expected: Optional[float] = Field(default=None, description="Expected calculated value")
    actual: Optional[float] = Field(default=None, description="Actual stated value")
    discrepancy_amount: Optional[float] = Field(default=None, description="Absolute difference")
    numeric_error: Optional[str] = Field(
        default=None,
        description="Formatted numeric error string, e.g. sum=12.40 total=13.00 delta=-0.60",
    )
    message: str = Field(default="", description="Human/LLM-readable discrepancy explanation")


# Backwards compatibility alias
ReconciliationCheck = CheckResult


class ReconciliationResult(BaseModel):
    """Summary of all deterministic checks."""

    is_valid: bool = Field(description="True if all mathematical checks pass")
    checks: List[CheckResult] = Field(default_factory=list)
    failing_row_indices: List[int] = Field(
        default_factory=list,
        description="0-based indices of line items associated with failing checks",
    )
    numeric_errors: List[str] = Field(
        default_factory=list,
        description="Exact numeric error strings ready for retry prompt",
    )
    discrepancies: List[str] = Field(
        default_factory=list,
        description="Human-readable discrepancy summary lines",
    )


class RetryLogEntry(BaseModel):
    """Record of a correction attempt fed back to LLM."""

    attempt: int = Field(description="Attempt sequence number (1, 2, ...)")
    timestamp: str = Field(description="ISO timestamp of retry")
    model_used: str = Field(description="LLM model identifier used")
    failing_rows_sent: List[dict] = Field(default_factory=list, description="Only failing rows sent to model")
    numeric_errors_sent: List[str] = Field(description="List of exact numeric errors given to model")
    patch_received: Optional[dict] = Field(default=None, description="JSON patch returned by model")
    resolved: bool = Field(description="Whether this retry resolved discrepancies")
    notes: Optional[str] = Field(default="", description="Additional context or outcome notes")


class ExtractionPayload(BaseModel):
    """Payload representing fully extracted and reconciled document state."""

    filename: str
    doc_total: DocumentTotal
    line_items: List[LineItem]
    reconciliation: Optional[ReconciliationResult] = None
    retry_log: List[RetryLogEntry] = Field(default_factory=list)
