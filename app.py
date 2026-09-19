"""Streamlit application for doc-reconciler (Option B).

Multi-page PDF / text extraction -> Pydantic models -> Deterministic Python checks -> Retry log -> Export.
"""

from __future__ import annotations

import io
import json
import os
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.models import (
    CheckResult,
    DocumentTotal,
    ExtractionPayload,
    LineItem,
    ReconciliationResult,
    RetryLogEntry,
)
from src.pdf_processor import PDFDocument
from src.checks import check_document, run_checks
from src.extract import extract_and_merge_document, extract_from_text
from src.retry import retry_reconciliation_loop
from src.agnes_client import get_agnes_client, get_available_providers, get_provider_client

load_dotenv()

st.set_page_config(
    page_title="Doc Reconciler",
    page_icon="🧾",
    layout="wide",
)

# ---------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------
if "doc_total" not in st.session_state:
    st.session_state.doc_total = DocumentTotal(
        subtotal=0.0,
        tax=0.0,
        shipping=0.0,
        discount=0.0,
        total=0.0,
        currency="USD",
        page=1,
        page_totals={},
        raw="",
    )

if "line_items" not in st.session_state:
    st.session_state.line_items = []

if "pdf_pages" not in st.session_state:
    st.session_state.pdf_pages = []

if "file_bytes" not in st.session_state:
    st.session_state.file_bytes = None

if "file_name" not in st.session_state:
    st.session_state.file_name = ""

if "file_type" not in st.session_state:
    st.session_state.file_type = ""

if "retry_log" not in st.session_state:
    st.session_state.retry_log = []

# ---------------------------------------------------------
# Sidebar Configuration
# ---------------------------------------------------------
st.sidebar.title("🧾 Doc Reconciler")
st.sidebar.caption("Deterministic Document Reconciliation (Option B)")

providers = get_available_providers()
selected_provider = None
if providers:
    selected_provider = st.sidebar.selectbox(
        "Active LLM Model",
        options=providers,
        format_func=lambda opt: opt.display_name,
        index=0,
    )
    st.sidebar.info(f"Target: `{selected_provider.model_id}`\nEndpoint: `{selected_provider.base_url or 'default'}`")
else:
    st.sidebar.warning("No API credentials detected in environment. Please set AGNESAI_API_KEY.")

tolerance = st.sidebar.slider(
    "Check Tolerance",
    min_value=0.00,
    max_value=1.00,
    value=0.01,
    step=0.01,
    help="Tolerance for rounding differences in currency checks (default: 0.01).",
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Fixtures & Samples")

txt_fixture_path = os.path.join("data", "fixtures", "invoice_mismatch.txt")
if os.path.exists(txt_fixture_path):
    if st.sidebar.button("📄 Load Fixture (invoice_mismatch.txt)"):
        with open(txt_fixture_path, "r", encoding="utf-8") as f:
            txt_content = f.read()
        st.session_state.file_bytes = txt_content.encode("utf-8")
        st.session_state.file_name = "invoice_mismatch.txt"
        st.session_state.file_type = "txt"
        st.session_state.pdf_pages = [{"page": 1, "text": txt_content}]
        st.sidebar.success("Loaded fixture: invoice_mismatch.txt")

pdf_fixture_path = os.path.join("data", "fixtures", "invoice_mismatch.pdf")
if os.path.exists(pdf_fixture_path):
    if st.sidebar.button("📂 Load Fixture (invoice_mismatch.pdf)"):
        with open(pdf_fixture_path, "rb") as f:
            f_bytes = f.read()
        st.session_state.file_bytes = f_bytes
        st.session_state.file_name = "invoice_mismatch.pdf"
        st.session_state.file_type = "pdf"
        doc = PDFDocument(f_bytes, filename="invoice_mismatch.pdf")
        st.session_state.pdf_pages = doc.get_all_pages_text()
        st.sidebar.success("Loaded fixture: invoice_mismatch.pdf (2 pages)")

if st.sidebar.button("Load Pre-set Sample Items"):
    st.session_state.doc_total = DocumentTotal(
        subtotal=25.00,
        tax=0.00,
        shipping=0.00,
        discount=0.00,
        total=26.00,
        currency="USD",
        page=1,
        page_totals={1: 26.00},
        raw="Subtotal: $26.00, Total: $26.00",
    )
    st.session_state.line_items = [
        LineItem(
            description="Standard Widget",
            qty=1.0,
            unit_price=10.0,
            amount=10.0,
            page=1,
            raw="1. Standard Widget | Qty: 1 | Unit Price: $10.00 | Amount: $10.00",
        ),
        LineItem(
            description="Premium Gadget",
            qty=1.0,
            unit_price=15.0,
            amount=15.0,
            page=1,
            raw="2. Premium Gadget | Qty: 1 | Unit Price: $15.00 | Amount: $15.00",
        ),
    ]
    st.session_state.file_name = "sample_mismatch.txt"
    st.session_state.file_type = "txt"
    st.session_state.pdf_pages = [{"page": 1, "text": "Sample text invoice with deliberate $26.00 total vs $25.00 sum"}]
    st.sidebar.success("Loaded pre-set deliberate mismatch sample (10+15=25 vs total 26).")

if st.sidebar.button("Clear Session Data"):
    st.session_state.line_items = []
    st.session_state.pdf_pages = []
    st.session_state.file_bytes = None
    st.session_state.file_name = ""
    st.session_state.file_type = ""
    st.session_state.retry_log = []
    st.session_state.doc_total = DocumentTotal(
        subtotal=0.0, tax=0.0, shipping=0.0, discount=0.0, total=0.0, currency="USD", page=1, page_totals={}, raw=""
    )
    st.rerun()

# ---------------------------------------------------------
# Main App Header & Tabs
# ---------------------------------------------------------
st.title("Document Reconciler (Option B)")
st.caption(
    "Option B Architecture: LLM extracts unstructured documents into Pydantic models. "
    "Python owns arithmetic and validation. Failing rows are fed back to Agnes for targeted patches."
)

tab_upload, tab_items, tab_checks, tab_retry, tab_export = st.tabs([
    "Upload",
    "Line items",
    "Checks",
    "Retry log",
    "Export",
])

# =========================================================
# TAB 1: Upload
# =========================================================
with tab_upload:
    st.header("1. Upload Multi-Page Document")
    st.write("Upload an invoice or financial receipt in PDF or plain text format.")

    uploaded_file = st.file_uploader("Upload Multi-page PDF or Text Stand-in Document", type=["pdf", "txt"])

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        st.session_state.file_bytes = file_bytes
        st.session_state.file_name = uploaded_file.name

        if uploaded_file.name.lower().endswith(".pdf"):
            st.session_state.file_type = "pdf"
            try:
                pdf_doc = PDFDocument(file_bytes, filename=uploaded_file.name)
                st.session_state.pdf_pages = pdf_doc.get_all_pages_text()
                st.success(f"Loaded '{uploaded_file.name}' — {pdf_doc.page_count} page(s) detected via PyMuPDF.")
            except Exception as err:
                st.error(f"Error parsing PDF with PyMuPDF: {err}")
        else:
            st.session_state.file_type = "txt"
            txt_content = file_bytes.decode("utf-8", errors="replace")
            st.session_state.pdf_pages = [{"page": 1, "text": txt_content}]
            st.success(f"Loaded text document '{uploaded_file.name}'.")

    if st.session_state.file_bytes and st.session_state.pdf_pages:
        if st.session_state.file_type == "pdf":
            pdf_doc = PDFDocument(st.session_state.file_bytes, filename=st.session_state.file_name)
            col_view, col_text = st.columns([1, 1])

            with col_view:
                st.subheader("Page View")
                page_sel = st.selectbox(
                    "Select page to preview",
                    options=list(range(1, pdf_doc.page_count + 1)),
                    index=0,
                )
                try:
                    img = pdf_doc.render_page_image(page_sel - 1, dpi=120)
                    st.image(img, caption=f"Page {page_sel}", width="stretch")
                except Exception as e:
                    st.warning(f"Could not render page image: {e}")

            with col_text:
                st.subheader("Extracted Page Text")
                selected_text = pdf_doc.get_page_text(page_sel - 1)
                st.text_area(
                    f"Raw Text (Page {page_sel})",
                    value=selected_text,
                    height=400,
                    disabled=True,
                )
        else:
            st.subheader("Document Text Content")
            st.text_area(
                f"File: {st.session_state.file_name}",
                value=st.session_state.pdf_pages[0]["text"],
                height=300,
                disabled=True,
            )

        st.markdown("---")
        col_act1, col_act2 = st.columns([2, 3])
        with col_act1:
            if st.button("🚀 Extract Line Items with Agnes AI", type="primary"):
                if not selected_provider:
                    st.error("No LLM provider available. Set AGNESAI_API_KEY.")
                else:
                    with st.spinner("Calling Agnes AI per-page extraction and merging..."):
                        try:
                            client = get_provider_client(selected_provider)
                            doc_tot, items = extract_and_merge_document(
                                pages=st.session_state.pdf_pages,
                                client=client,
                                model=selected_provider.model_id,
                            )
                            st.session_state.doc_total = doc_tot
                            st.session_state.line_items = items
                            st.success(f"Extracted {len(items)} line item(s). Stated total: {doc_tot.total}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Extraction failed: {e}")

        with col_act2:
            st.caption("Extracted models will populate the 'Line items' and 'Checks' tabs automatically.")

# =========================================================
# TAB 2: Line items
# =========================================================
with tab_items:
    st.header("2. Extracted Line Items & Totals (Pydantic Models)")

    if not st.session_state.line_items:
        st.info("No line items extracted yet. Upload a document and extract in the Upload tab, or load sample data from the sidebar.")
    else:
        st.subheader("Stated Document Figures")
        tot = st.session_state.doc_total
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Stated Subtotal", f"{tot.currency} {tot.subtotal:.2f}" if tot.subtotal is not None else "N/A")
        m2.metric("Stated Tax", f"{tot.currency} {tot.tax:.2f}" if tot.tax is not None else "$0.00")
        m3.metric("Stated Grand Total", f"{tot.currency} {tot.total:.2f}" if tot.total is not None else "N/A")
        m4.metric("Item Count", len(st.session_state.line_items))

        if tot.page_totals:
            st.caption(f"Page totals recorded: {tot.page_totals}")

        st.subheader("Line Items Table")
        table_rows = []
        for idx, item in enumerate(st.session_state.line_items):
            expected = round(item.qty * item.unit_price, 2) if item.qty and item.unit_price else None
            math_match = (
                "✅" if (item.amount is not None and expected is not None and abs(item.amount - expected) <= tolerance)
                else "❌" if (item.amount is not None and expected is not None)
                else "⚠️"
            )
            table_rows.append({
                "Index": idx,
                "Page": item.page,
                "Description": item.description,
                "Quantity": item.qty,
                "Unit Price": item.unit_price,
                "Stated Amount": item.amount,
                "Calculated": expected,
                "Math Status": math_match,
                "Raw Text": item.raw[:50] + ("..." if len(item.raw) > 50 else ""),
            })

        df_items = pd.DataFrame(table_rows)
        st.dataframe(df_items, use_container_width=True)

# =========================================================
# TAB 3: Checks
# =========================================================
with tab_checks:
    st.header("3. Deterministic Python Checks (No LLM)")
    st.write(
        "Checks run purely in Python: `sum(items) == total`, `qty * price == amount`, `duplicate rows`, "
        "and `page-1 vs last page total`."
    )

    if not st.session_state.line_items:
        st.info("No items loaded to check. Upload a document or load sample data.")
    else:
        results: ReconciliationResult = run_checks(
            doc_total=st.session_state.doc_total,
            line_items=st.session_state.line_items,
            tolerance=tolerance,
        )

        if results.is_valid:
            st.success("✅ ALL DETERMINISTIC CHECKS PASSED! Arithmetic and integrity verified by Python.")
        else:
            st.error(f"❌ RECONCILIATION FAILED! {len(results.discrepancies)} discrepancy(ies) detected.")

        st.subheader("Checks Breakdown")
        check_table = []
        for c in results.checks:
            check_table.append({
                "Status": "✅ PASS" if c.passed else "❌ FAIL",
                "Check Name": c.name,
                "Expected / Calculated": f"{c.expected:.2f}" if c.expected is not None else "-",
                "Actual / Stated": f"{c.actual:.2f}" if c.actual is not None else "-",
                "Discrepancy": f"{c.discrepancy_amount:.2f}" if c.discrepancy_amount else "-",
                "Numeric Error (Sent to Agnes)": c.numeric_error or "-",
                "Details": c.message,
            })
        st.dataframe(pd.DataFrame(check_table), use_container_width=True)

        if not results.is_valid:
            st.markdown("### Discrepancies & Numeric Errors")
            for err in results.numeric_errors:
                st.code(err, language="text")

            st.markdown("---")
            st.subheader("Option B Targeted Feedback Retry")
            st.write(
                "Send ONLY the failing rows and exact numeric discrepancies to Agnes AI. "
                "Agnes returns a JSON correction patch, and Python verifies the math up to 3 times."
            )

            if st.button("⚡ Trigger Agnes Retry Loop", type="primary"):
                if not selected_provider:
                    st.error("No LLM provider available.")
                else:
                    with st.spinner("Running Option B feedback loop with Agnes AI..."):
                        try:
                            client = get_provider_client(selected_provider)
                            new_tot, new_items, final_res, new_logs = retry_reconciliation_loop(
                                doc_total=st.session_state.doc_total,
                                line_items=st.session_state.line_items,
                                tolerance=tolerance,
                                max_retries=3,
                                client=client,
                                model=selected_provider.model_id,
                            )
                            st.session_state.doc_total = new_tot
                            st.session_state.line_items = new_items
                            st.session_state.retry_log.extend(new_logs)

                            if final_res.is_valid:
                                st.success("Agnes retry loop succeeded! All mathematical checks now pass.")
                            else:
                                st.warning(f"Retry loop completed 3 attempts. Remaining discrepancies: {len(final_res.discrepancies)}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Retry loop failed: {e}")

# =========================================================
# TAB 4: Retry log
# =========================================================
with tab_retry:
    st.header("4. Retry Audit Trail")
    st.write("Detailed log of correction attempts sent to Agnes AI and received JSON patches.")

    if not st.session_state.retry_log:
        st.info("No retries triggered yet. If checks fail on the Checks tab, click 'Trigger Agnes Retry Loop'.")
    else:
        st.metric("Total Retry Attempts Recorded", len(st.session_state.retry_log))

        for entry in reversed(st.session_state.retry_log):
            status_badge = "✅ Resolved" if entry.resolved else "⚠️ Unresolved"
            with st.expander(f"Attempt #{entry.attempt} — {entry.timestamp} [{status_badge}]", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Numeric Errors Sent to Model:**")
                    for err in entry.numeric_errors_sent:
                        st.code(err, language="text")

                    st.markdown(f"**Failing Rows Sent ({len(entry.failing_rows_sent)} rows):**")
                    st.json(entry.failing_rows_sent)

                with c2:
                    st.markdown("**JSON Patch Received from Model:**")
                    st.json(entry.patch_received or {})
                    st.markdown(f"**Notes / Outcome:** {entry.notes}")

# =========================================================
# TAB 5: Export
# =========================================================
with tab_export:
    st.header("5. Export Reconciled Data & Reports")

    if not st.session_state.line_items:
        st.info("No data available to export.")
    else:
        current_res = run_checks(st.session_state.doc_total, st.session_state.line_items, tolerance=tolerance)

        payload = ExtractionPayload(
            filename=st.session_state.file_name or "reconciled_document",
            doc_total=st.session_state.doc_total,
            line_items=st.session_state.line_items,
            reconciliation=current_res,
            retry_log=st.session_state.retry_log,
        )

        st.subheader("Data Summary")
        st.write(f"Status: **{'PASSED' if current_res.is_valid else 'FAILED'}**")
        st.write(f"Total Line Items: **{len(st.session_state.line_items)}**")
        st.write(f"Stated Total: **{st.session_state.doc_total.currency} {st.session_state.doc_total.total}**")

        st.markdown("---")
        st.subheader("Download Artifacts")

        col_d1, col_d2, col_d3 = st.columns(3)

        with col_d1:
            json_str = payload.model_dump_json(indent=2)
            st.download_button(
                label="📥 Download JSON Payload",
                data=json_str,
                file_name=f"{payload.filename}_reconciled.json",
                mime="application/json",
            )

        with col_d2:
            export_rows = [it.model_dump() for it in st.session_state.line_items]
            csv_str = pd.DataFrame(export_rows).to_csv(index=False)
            st.download_button(
                label="📥 Download Line Items CSV",
                data=csv_str,
                file_name=f"{payload.filename}_items.csv",
                mime="text/csv",
            )

        with col_d3:
            md_report = (
                f"# Reconciliation Report: {payload.filename}\n\n"
                f"- **Timestamp**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"- **Overall Status**: {'PASSED' if current_res.is_valid else 'FAILED'}\n"
                f"- **Stated Total**: {st.session_state.doc_total.total}\n"
                f"- **Calculated Sum**: {round(sum(it.amount for it in st.session_state.line_items if it.amount is not None), 2)}\n\n"
                "## Checks\n"
            )
            for c in current_res.checks:
                md_report += f"- [{'x' if c.passed else ' '}] {c.name}: {c.message}\n"

            st.download_button(
                label="📥 Download Markdown Summary",
                data=md_report,
                file_name=f"{payload.filename}_report.md",
                mime="text/markdown",
            )
