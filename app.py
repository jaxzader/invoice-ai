"""
AI Invoice Processor - Streamlit app.
Run locally with:  streamlit run app.py
"""

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from extractor import DEFAULT_MODEL, extract_invoice, read_pdf_text, validate_invoice

st.set_page_config(page_title="AI Invoice Processor", page_icon="🧾", layout="wide")


def get_api_key() -> str | None:
    """Look for the Groq key in Streamlit secrets, then env vars, then the sidebar."""
    try:
        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass  # no secrets file locally, that's fine
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    return st.sidebar.text_input("Groq API key", type="password", help="Free at console.groq.com/keys")


# ---------- Header ----------
st.title("🧾 AI Invoice Processor")
st.write(
    "Upload invoice PDFs. An LLM pulls out the vendor, dates, line items, and totals, "
    "then Python double-checks the math and flags duplicates so a person only reviews the problem invoices."
)

api_key = get_api_key()
model = st.sidebar.text_input("Model", value=DEFAULT_MODEL)
st.sidebar.caption(
    "The sample invoices are fictional. Two have planted problems: a math error and a duplicate."
)

SAMPLE_DIR = Path(__file__).parent / "sample_invoices"
sample_paths = sorted(SAMPLE_DIR.glob("*.pdf"))


def process(files):
    """Run extraction + validation on a list of (name, file) pairs and save the results."""
    results = []
    seen = set()  # tracks vendor + invoice number for duplicate detection
    progress = st.progress(0.0, text="Starting...")

    for i, (name, file) in enumerate(files, start=1):
        progress.progress(i / len(files), text=f"Reading {name}...")
        try:
            text = read_pdf_text(file)
            if not text:
                raise ValueError("No text found. This might be a scanned image PDF.")
            data = extract_invoice(text, api_key, model)
            issues = validate_invoice(data, seen)
            results.append({"file": name, "data": data, "issues": issues, "error": None})
        except Exception as e:
            results.append({"file": name, "data": None, "issues": [], "error": str(e)})

    progress.empty()
    st.session_state["results"] = results


uploaded_files = st.file_uploader("Upload invoice PDFs", type="pdf", accept_multiple_files=True)

if not api_key:
    st.warning("Add a Groq API key in the sidebar to process invoices.")
    st.stop()

# ---------- Process ----------
if uploaded_files:
    if st.button("Process invoices", type="primary"):
        process([(f.name, f) for f in uploaded_files])
else:
    st.info("Upload your own invoice PDFs, or try it instantly with 7 sample invoices.")
    if sample_paths and st.button("▶ Try the sample invoices", type="primary"):
        process([(p.name, p) for p in sample_paths])

results = st.session_state.get("results")
if not results:
    st.stop()

# ---------- Summary ----------
ok = [r for r in results if r["data"] and not r["issues"]]
flagged = [r for r in results if r["data"] and r["issues"]]
failed = [r for r in results if r["error"]]
total_value = sum(float(r["data"].get("total") or 0) for r in results if r["data"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Invoices processed", len(results))
c2.metric("Passed checks", len(ok))
c3.metric("Need review", len(flagged) + len(failed))
c4.metric("Total value", f"${total_value:,.2f}")

# ---------- Summary table ----------
summary_rows, line_rows = [], []
for r in results:
    d = r["data"] or {}
    if r["error"]:
        status = "❌ Error"
    elif r["issues"]:
        status = "⚠️ Review"
    else:
        status = "✅ OK"
    summary_rows.append({
        "Status": status,
        "File": r["file"],
        "Vendor": d.get("vendor_name"),
        "Invoice #": d.get("invoice_number"),
        "Invoice date": d.get("invoice_date"),
        "Due date": d.get("due_date"),
        "Subtotal": d.get("subtotal"),
        "Tax": d.get("tax"),
        "Total": d.get("total"),
        "Issues": "; ".join(r["issues"]) or r["error"] or "",
    })
    for item in d.get("line_items") or []:
        line_rows.append({"Vendor": d.get("vendor_name"), "Invoice #": d.get("invoice_number"), **item})

summary_df = pd.DataFrame(summary_rows)
st.subheader("Results")
st.dataframe(summary_df, width="stretch", hide_index=True)

d1, d2 = st.columns(2)
d1.download_button("Download invoice summary (CSV)", summary_df.to_csv(index=False), "invoice_summary.csv", "text/csv")
if line_rows:
    d2.download_button("Download line items (CSV)", pd.DataFrame(line_rows).to_csv(index=False), "line_items.csv", "text/csv")

# ---------- Detail view ----------
st.subheader("Invoice details")
for r in results:
    icon = "❌" if r["error"] else ("⚠️" if r["issues"] else "✅")
    with st.expander(f"{icon} {r['file']}"):
        if r["error"]:
            st.error(r["error"])
            continue
        for issue in r["issues"]:
            st.warning(issue)
        d = r["data"]
        st.write(f"**Vendor:** {d.get('vendor_name')}  |  **Invoice #:** {d.get('invoice_number')}  |  **Date:** {d.get('invoice_date')}")
        if d.get("line_items"):
            st.dataframe(pd.DataFrame(d["line_items"]), width="stretch", hide_index=True)
        with st.popover("Raw JSON"):
            st.json(d)
