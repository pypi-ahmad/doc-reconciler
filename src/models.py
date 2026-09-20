"""Pydantic data models for document reconciliation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    """Represent one extracted invoice, receipt, or financial-document row.

    Attributes:
        sku: Optional source item identifier.
        desc: Preferred item description.
        qty: Stated quantity.
        unit_price: Stated price per unit.
        amount: Stated line amount.
        page: One-based source page number.
        raw: Source text that supports the extracted row.
        description: Compatibility alias synchronized with ``desc``.
    """

    sku: str | None = Field(default=None, description="Optional item identifier")
    desc: str | None = Field(default=None, description="Item description")
    qty: float | None = Field(default=None, description="Item quantity")
    unit_price: float | None = Field(default=None, description="Item unit price")
    amount: float | None = Field(default=None, description="Total amount for line item")
    page: int = Field(default=1, description="Source page number (1-indexed)")
    raw: str = Field(default="", description="Exact raw text snippet from document")
    description: str | None = Field(default="", description="Description or product name")

    def model_post_init(self, _context: Any) -> None:
        """Synchronize the preferred and compatibility description fields.

        Args:
            _context: Pydantic model-construction context, unused by this model.
        """
        if not self.desc and self.description:
            self.desc = self.description
        elif self.desc and not self.description:
            self.description = self.desc


class DocumentTotal(BaseModel):
    """Represent detailed stated totals used by checks and compatibility APIs.

    Attributes:
        subtotal: Amount before taxes, discounts, or shipping.
        tax: Stated tax amount.
        shipping: Stated shipping or handling amount.
        discount: Stated discount amount.
        total: Stated grand total.
        currency: Currency symbol or three-letter code.
        page: Source page of the grand total.
        page_totals: Per-page stated totals for page consistency checks.
        raw: Source totals text.
    """

    subtotal: float | None = Field(default=None, description="Subtotal before taxes/discounts")
    tax: float | None = Field(default=None, description="Tax amount")
    shipping: float | None = Field(default=None, description="Shipping or handling fee")
    discount: float | None = Field(default=None, description="Discounts applied")
    total: float | None = Field(default=None, description="Grand total stated on document")
    currency: str = Field(default="USD", description="Currency symbol or 3-letter code")
    page: int | None = Field(default=1, description="Page number where grand total appears")
    page_totals: dict[int, float] = Field(
        default_factory=dict,
        description="Stated totals per page: {page_num: stated_page_total}",
    )
    raw: str = Field(default="", description="Raw text snippet of totals summary")


class DocumentTotals(BaseModel):
    """Represent stated totals used by the active reconciliation pipeline.

    Attributes:
        subtotal: Optional stated subtotal.
        tax: Optional stated tax.
        total: Optional stated grand total.
        page: Optional source page for the total.
    """

    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    page: int | None = None


class ExtractionResult(BaseModel):
    """Represent the strict Agnes extraction schema.

    Attributes:
        items: Extracted line items.
        totals: Stated summary totals.
        notes: Extraction notes that do not alter source values.
    """

    items: list[LineItem] = Field(default_factory=list)
    totals: DocumentTotals = Field(default_factory=DocumentTotals)
    notes: str = ""


class CheckResult(BaseModel):
    """Represent one deterministic mathematical or integrity check.

    Attributes:
        name: Check identifier.
        ok: Canonical pass/fail state.
        passed: Compatibility alias for ``ok``.
        expected: Python-calculated value.
        actual: Stated source value.
        delta: ``expected - actual``.
        detail: Human-readable explanation.
        discrepancy_amount: Absolute numeric delta.
        numeric_error: Retry-ready numeric context for failed checks.
        message: Compatibility alias for ``detail``.
    """

    name: str = Field(description="Name or category of the check")
    ok: bool | None = Field(default=None, description="Whether the check succeeded")
    passed: bool | None = Field(default=None, description="Compatibility name for ok")
    expected: float | None = Field(default=None, description="Expected calculated value")
    actual: float | None = Field(default=None, description="Actual stated value")
    delta: float | None = Field(default=None, description="Calculated minus stated value")
    detail: str = Field(default="", description="Human-readable check detail")
    discrepancy_amount: float | None = Field(default=None, description="Absolute difference")
    numeric_error: str | None = Field(
        default=None,
        description="Formatted numeric error string, e.g. sum=12.40 total=13.00 delta=-0.60",
    )
    message: str = Field(default="", description="Human/LLM-readable discrepancy explanation")

    def model_post_init(self, _context: Any) -> None:
        """Populate compatibility aliases and derive an omitted numeric delta.

        Args:
            _context: Pydantic model-construction context, unused by this model.
        """
        if self.ok is None:
            self.ok = bool(self.passed)
        if self.passed is None:
            self.passed = bool(self.ok)
        if self.delta is None and self.expected is not None and self.actual is not None:
            self.delta = round(self.expected - self.actual, 2)
        if not self.detail and self.message:
            self.detail = self.message
        elif self.detail and not self.message:
            self.message = self.detail


# Backwards compatibility alias
ReconciliationCheck = CheckResult


class ReconciliationResult(BaseModel):
    """Summarize all deterministic checks for one document.

    Attributes:
        is_valid: True only when every produced check passes.
        checks: Individual deterministic outcomes.
        failing_row_indices: Zero-based rows relevant to failed checks.
        numeric_errors: Exact numeric messages for retry prompts.
        discrepancies: Human-readable failure details.
    """

    is_valid: bool = Field(description="True if all mathematical checks pass")
    checks: list[CheckResult] = Field(default_factory=list)
    failing_row_indices: list[int] = Field(
        default_factory=list,
        description="0-based indices of line items associated with failing checks",
    )
    numeric_errors: list[str] = Field(
        default_factory=list,
        description="Exact numeric error strings ready for retry prompt",
    )
    discrepancies: list[str] = Field(
        default_factory=list,
        description="Human-readable discrepancy summary lines",
    )


class RetryLogEntry(BaseModel):
    """Record one compatibility-format correction attempt sent to Agnes.

    Attributes:
        attempt: One-based retry sequence number.
        timestamp: ISO timestamp recorded for the attempt.
        model_used: Model identifier used for the request.
        failing_rows_sent: Source rows included in the narrow patch request.
        numeric_errors_sent: Exact discrepancies provided to the model.
        patch_received: Parsed JSON patch, when available.
        resolved: Whether Python checks passed after the patch.
        notes: Additional outcome context.
    """

    attempt: int = Field(description="Attempt sequence number (1, 2, ...)")
    timestamp: str = Field(description="ISO timestamp of retry")
    model_used: str = Field(description="LLM model identifier used")
    failing_rows_sent: list[dict[str, Any]] = Field(
        default_factory=list, description="Only failing rows sent to model"
    )
    numeric_errors_sent: list[str] = Field(description="Exact numeric errors given to model")
    patch_received: dict | None = Field(default=None, description="JSON patch returned by model")
    resolved: bool = Field(description="Whether this retry resolved discrepancies")
    notes: str | None = Field(default="", description="Additional context or outcome notes")


class ExtractionPayload(BaseModel):
    """Represent the legacy complete extraction and reconciliation payload.

    Attributes:
        filename: Source file name.
        doc_total: Detailed stated totals.
        line_items: Extracted document rows.
        reconciliation: Optional deterministic result summary.
        retry_log: Compatibility-format retry records.
    """

    filename: str
    doc_total: DocumentTotal
    line_items: list[LineItem]
    reconciliation: ReconciliationResult | None = None
    retry_log: list[RetryLogEntry] = Field(default_factory=list)


class PageExtraction(BaseModel):
    """Represent the legacy contract for one extracted page.

    Attributes:
        line_items: Page rows.
        page_total: Stated total for this page.
        subtotal: Stated subtotal.
        tax: Stated tax.
        shipping: Stated shipping amount.
        discount: Stated discount amount.
        grand_total: Stated grand total.
        currency: Stated currency code.
    """

    line_items: list[LineItem] = Field(default_factory=list)
    page_total: float | None = None
    subtotal: float | None = None
    tax: float | None = None
    shipping: float | None = None
    discount: float | None = None
    grand_total: float | None = None
    currency: str = "USD"


class CorrectedRow(BaseModel):
    """Represent one row correction in the legacy retry-patch contract.

    Attributes:
        row_index: Zero-based target line-item index.
        description: Replacement description, when supported by evidence.
        qty: Replacement quantity.
        unit_price: Replacement unit price.
        amount: Replacement line amount.
    """

    row_index: int
    description: str | None = None
    qty: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class RetryPatch(BaseModel):
    """Represent the legacy retry response from Agnes.

    Attributes:
        corrected_rows: Supported line-item corrections.
        corrected_total: Supported replacement grand total.
        corrected_subtotal: Supported replacement subtotal.
        explanation: Provider explanation that never decides Python validity.
    """

    corrected_rows: list[CorrectedRow] = Field(default_factory=list)
    corrected_total: float | None = None
    corrected_subtotal: float | None = None
    explanation: str = ""


class ReconcileState(BaseModel):
    """Represent session-safe state for the active Streamlit pipeline.

    Attributes:
        items: Current extracted or patched line items.
        totals: Current stated totals.
        checks: Most recent deterministic check results.
        retries: Serialized retry attempts.
        texts: Ingested page text in source order.
    """

    items: list[LineItem] = Field(default_factory=list)
    totals: DocumentTotals = Field(default_factory=DocumentTotals)
    checks: list[CheckResult] = Field(default_factory=list)
    retries: list[dict[str, Any]] = Field(default_factory=list)
    texts: list[str] = Field(default_factory=list)
