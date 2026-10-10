"""Simple and clean Streamlit interface for batch document metadata extraction.

Upload one or multiple documents (.docx or scanned images), extract the six
metadata fields, preview the results in a clean table, and download them as
CSV or JSON.
"""
from __future__ import annotations

import csv
from datetime import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import time

import streamlit as st

# Ensure src/ is on sys.path
SOURCE_DIR = Path(__file__).resolve().parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from evidence_locator import locate_all_evidence
from read_documents import SUPPORTED_SUFFIXES, extract_text
from schema import CSV_TO_FIELD, AgreementFields
from semantic_extractor import DEFAULT_MODEL, extract_fields

FIELD_COLUMNS = list(CSV_TO_FIELD)
UPLOAD_EXTENSIONS = [s.lstrip(".") for s in sorted(SUPPORTED_SUFFIXES)]


def make_combined_csv(records: list[dict[str, str | None]]) -> str:
    """Generate CSV with assignment column headers for multiple files."""
    buffer = io.StringIO(newline="")
    fieldnames = ["File Name", *FIELD_COLUMNS]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in records:
        writer.writerow({k: row.get(k, None) for k in fieldnames})
    return buffer.getvalue()


def clean_document_id(filename: str) -> str:
    """Normalize file stem for assignment naming."""
    lower = filename.lower()
    if lower.endswith(".pdf.docx"):
        return filename[:-len(".pdf.docx")]
    return Path(filename).stem


def main() -> None:
    st.set_page_config(page_title="Document Metadata Extractor", page_icon="📄", layout="centered")

    st.title("📄 Document Metadata Extractor")
    st.write(
        "Upload one or more documents (`.docx` or scanned images). "
        "The system will extract the six required metadata fields from each file and provide CSV & JSON downloads."
    )

    # Multi-file uploader
    uploaded_files = st.file_uploader(
        "Upload document(s)",
        type=UPLOAD_EXTENSIONS,
        accept_multiple_files=True,
        help="Upload one or multiple .docx, .png, .jpg, .jpeg, .tiff, or .bmp files.",
    )

    if not uploaded_files:
        st.info("👆 Please upload one or more files above to begin.")
        return

    st.write(f"**{len(uploaded_files)} file(s) selected.**")

    # Extract Button
    if st.button("🚀 Extract Metadata", type="primary", use_container_width=True):
        results_list: list[dict[str, str | None]] = []
        full_json_records: list[dict] = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, file in enumerate(uploaded_files):
            file_name = Path(file.name.replace("\\", "/")).name
            doc_id = clean_document_id(file_name)
            status_text.text(f"Processing ({idx + 1}/{len(uploaded_files)}): {file_name}...")

            try:
                # Save file to temporary folder for processing
                with tempfile.TemporaryDirectory(prefix="simple_extract_") as tmp_dir:
                    tmp_file = Path(tmp_dir) / file_name
                    tmp_file.write_bytes(file.getvalue())

                    # 1. Text extraction / OCR
                    text = extract_text(tmp_file)

                    # 2. Semantic extraction via local model
                    fields: AgreementFields = extract_fields(text)

                    # 3. Evidence grounding
                    evidence = locate_all_evidence(fields, text)

                row = {"File Name": doc_id, **fields.to_assignment_columns()}
                results_list.append(row)

                full_json_records.append({
                    "document_id": doc_id,
                    "filename": file_name,
                    "fields": fields.to_assignment_columns(),
                    "evidence": {k: v.get("evidence") for k, v in evidence.items()},
                    "character_count": len(text),
                })

            except Exception as exc:
                st.error(f"Failed to process '{file_name}': {exc}")
                # Append blank row for failed file
                results_list.append({
                    "File Name": doc_id,
                    **{col: None for col in FIELD_COLUMNS},
                })
                full_json_records.append({
                    "document_id": doc_id,
                    "filename": file_name,
                    "error": str(exc),
                    "fields": {col: None for col in FIELD_COLUMNS},
                })

            progress_bar.progress((idx + 1) / len(uploaded_files))

        status_text.success(f"✅ Successfully processed {len(uploaded_files)} file(s)!")
        time.sleep(0.3)
        progress_bar.empty()

        # Save in session state so results persist across re-renders
        st.session_state["results_csv_rows"] = results_list
        st.session_state["results_json"] = full_json_records

    # Display results if available in session_state
    if "results_csv_rows" in st.session_state and st.session_state["results_csv_rows"]:
        st.markdown("### 📊 Extracted Results")
        
        # Display clean dataframe/table
        st.dataframe(
            st.session_state["results_csv_rows"],
            use_container_width=True,
            hide_index=True,
        )

        # Download buttons
        csv_data = make_combined_csv(st.session_state["results_csv_rows"]).encode("utf-8-sig")
        json_data = json.dumps(st.session_state["results_json"], indent=2, ensure_ascii=False).encode("utf-8")

        col_csv, col_json = st.columns(2)
        with col_csv:
            st.download_button(
                "📥 Download CSV",
                data=csv_data,
                file_name=f"extracted_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col_json:
            st.download_button(
                "📥 Download JSON",
                data=json_data,
                file_name=f"extracted_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )


if __name__ == "__main__":
    main()
