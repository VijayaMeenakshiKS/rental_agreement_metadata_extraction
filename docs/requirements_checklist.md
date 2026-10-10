# Rental Agreement Metadata Extraction

## Goal
Extract the six required metadata fields from the supplied rental agreements, keep evidence for review, and evaluate predictions against the assignment labels where valid ground truth is available.

## Current status
The code, documentation, test predictions, and evaluation reports are in this folder. Original files under `data/` are kept unchanged. The latest short-name prompt revision still needs one final local model refresh and evaluation.

## Requirements checklist
- [x] Found `data/train.csv`, `data/test.csv`, and document folders.
- [x] Identified Word documents (`.docx`) and image documents (`.png`). Two Word filenames end in `.pdf.docx`; their actual extension is still `.docx`.
- [x] Identified the six assignment columns: `Aggrement Value`, `Aggrement Start Date`, `Aggrement End Date`, `Renewal Notice (Days)`, `Party One`, `Party Two`.
- [ ] Confirm the authoritative train/test split and resolve the mismatched training row/document; no authoritative clarification was supplied.
- [x] Implement local text reading for Word files and OCR for image files.
- [x] Add semantic extraction using the configured local pretrained Ollama model; no fabricated values are substituted.
- [x] Use semantic model interpretation for fields; OCR only reads image text, with no regex/static layout extraction.
- [x] Validate the six-field output schema and normalize values for metric comparison.
- [x] Generate predictions for all actual test documents and evaluate against available ground truth.
- [x] Add beginner setup instructions, privacy notes, limitations, and reproducible commands.
- [x] Provide a polished, professional interactive Streamlit interface for DOCX and common scanned image formats.
- [x] Optional FastAPI RESTful web service wrapper implemented in `src/api.py` with `/extract`, `/health`, `/metrics`, and interactive Swagger documentation at `/docs`.


## Data audit notes
- `train.csv` has 10 rows and `data/train/` has 10 documents, but `24158401-Rental-Agreement` is listed in the CSV while its PNG is in `data/test/`; `46239065-Standard-Rental-Agreement-Rental-With-Performance-Fee.docx` is in `data/train/` without a matching CSV row.
- `24158401-Rental-Agreement` appears in both CSVs with identical labels. Treat this as possible train/test leakage and document it; do not use the training label as a prediction.
- One training row has a blank renewal notice label.
- Three training end dates do not exist in the calendar (`31.11.2009`, `31.04.2011`, `31.02.2011`). Preserve source labels and investigate against document evidence before deciding evaluation behavior.
- No README or rubric was present in the supplied project folder at the time of inspection.

## Implemented architecture

```text
DOCX / PNG -> document reader / OCR -> agreement text -> semantic extractor
     -> schema and value validation -> predictions + evidence -> field-level evaluation
```

OCR is only for reading text from image files. It does not perform the semantic extraction.

## Current implementation notes

The local Ollama call uses structured JSON output and runs on `localhost`. The test set contains four documents, including one ID also present in `train.csv`, so its metrics are only a small diagnostic. The evaluator supports the supplied date spellings, including dotted dates, two-digit years, ordinal day suffixes, and the `of`/asterisk forms found in the labels. The predictions themselves are preserved; normalization is for scoring only.
