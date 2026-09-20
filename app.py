"""Streamlit interface for local document reconciliation and Python verification."""

from __future__ import annotations

import hashlib
import os

import httpx
import pandas as pd
import streamlit as st

from src.config import get_settings
from src.ingest import ingest_document
from src.models import ReconcileState
from src.pipeline import reconcile_ingest

st.set_page_config(page_title="Document Reconciler", page_icon="📄", layout="wide")

settings = get_settings()
st.session_state.setdefault("reconcile_state", ReconcileState())
st.session_state.setdefault("upload_signature", None)
st.session_state.setdefault("last_ingest", None)
st.session_state.setdefault("extraction_notes", "")
state: ReconcileState = st.session_state.reconcile_state


@st.cache_data(ttl=10, max_entries=4)
def ollama_model_present(host: str, model: str) -> bool:
    """Return whether the configured Ollama model is locally available.

    Args:
        host: Base URL of the local Ollama service.
        model: Required OCR model name or tag.

    Returns:
        True when the service responds and lists the requested model; otherwise
        False. Connection and payload failures are deliberately treated as an
        unavailable health status.
    """
    try:
        response = httpx.get(f"{host}/api/tags", timeout=1.0)
        response.raise_for_status()
        names = [entry.get("name", "") for entry in response.json().get("models", [])]
        return any(name == model or name.startswith(f"{model}:") for name in names)
    except (httpx.HTTPError, ValueError, TypeError):
        return False


st.title("Document Reconciler")
st.caption("Review extracted values, Python checks, and retry records.")

with st.sidebar:
    st.header("Settings")
    tolerance = st.slider(
        "Tolerance",
        min_value=0.0,
        max_value=1.0,
        value=0.01,
        step=0.01,
    )
    max_retries = st.number_input(
        "Maximum retries",
        min_value=3,
        max_value=3,
        value=3,
        disabled=True,
    )
    force_ocr = st.checkbox("Force OCR", value=False)
    st.caption(f"Tolerance: {tolerance:.2f} · Retries: {max_retries} · Force OCR: {force_ocr}")

health, upload, line_items, checks, retry_log, export = st.tabs(
    ["Health", "Upload", "Line items", "Checks", "Retry log", "Export"]
)

with health:
    st.header("Health")
    key_set = bool(os.environ.get("AGNESAI_API_KEY"))
    model_present = ollama_model_present(settings.ollama_host, settings.ollama_ocr_model)
    left, right = st.columns(2)
    left.metric("AGNESAI_API_KEY set", "Yes" if key_set else "No")
    right.metric("Ollama OCR model present", "Yes" if model_present else "No")
    st.info("Health checks never print secrets and make no Agnes request.")

with upload:
    st.header("Upload")
    uploaded = st.file_uploader("Invoice-like PDF or text", type=["pdf", "txt"])
    if uploaded is not None:
        content = uploaded.getvalue()
        signature = hashlib.sha256(content + str(force_ocr).encode()).hexdigest()
        if signature != st.session_state.upload_signature:
            st.session_state.upload_signature = signature
            try:
                st.session_state.last_ingest = ingest_document(
                    content,
                    filename=uploaded.name,
                    force_ocr=force_ocr,
                )
            except (OSError, RuntimeError, ValueError) as error:
                st.session_state.last_ingest = None
                st.error(f"Ingest failed: {error}")

    ingest_result = st.session_state.last_ingest
    if ingest_result is not None:
        state.texts = [page["text"] for page in ingest_result["pages"]]
        st.success(
            f"Route: {ingest_result['route']} · Type: {ingest_result['pdf_type']} · "
            f"Pages: {len(ingest_result['pages'])}"
        )
        st.text_area(
            "Text preview",
            ingest_result["text"],
            height=320,
            disabled=True,
        )

with line_items:
    st.header("Line items")
    ingest_result = st.session_state.last_ingest
    if st.button(
        "Run full reconciliation",
        type="primary",
        disabled=ingest_result is None or not bool(settings.agnes_api_key),
    ):
        try:
            with st.spinner("Extracting, checking, and retrying failures..."):
                state = reconcile_ingest(
                    ingest_result,
                    tolerance=tolerance,
                    max_retries=int(max_retries),
                )
                st.session_state.reconcile_state = state
        except Exception as error:  # noqa: BLE001 - UI boundary reports provider/schema errors
            st.error(f"Reconciliation failed: {error}")

    st.subheader("Stated totals")
    st.json(state.totals.model_dump())
    if state.items:
        st.subheader("Extracted line items")
        st.dataframe(pd.DataFrame([item.model_dump() for item in state.items]))
    else:
        st.info("No extracted line items yet.")

with checks:
    st.header("Checks")
    if state.checks:
        if all(bool(check.ok) for check in state.checks):
            st.success("All Python checks pass.")
        else:
            st.error("One or more Python checks still fail.")
        st.dataframe(pd.DataFrame([check.model_dump() for check in state.checks]))
    else:
        st.info("No arithmetic checks yet.")

with retry_log:
    st.header("Retry log")
    if state.retries:
        for entry in state.retries:
            status = "all ok" if entry["all_ok"] else "still failing"
            with st.expander(f"Attempt {entry['attempt']} · {status}"):
                st.code(entry["numeric_error"], language="text")
                st.markdown("Failed checks before patch")
                st.dataframe(pd.DataFrame(entry["failed_checks"]))
                st.markdown("Failing rows sent")
                st.json(entry["failing_rows"])
                st.markdown("Agnes patch")
                st.json(entry["patch"])
                st.markdown("Python checks after patch")
                st.dataframe(pd.DataFrame(entry["checks_after"]))
    else:
        st.info("No retries yet. Maximum configured retries: 3.")

with export:
    st.header("Export")
    st.download_button(
        "Download state JSON",
        data=state.model_dump_json(indent=2),
        file_name="reconcile_state.json",
        mime="application/json",
        icon=":material/download:",
    )
