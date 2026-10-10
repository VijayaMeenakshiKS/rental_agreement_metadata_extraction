# Rental Agreement Metadata Extraction

A local Python project that reads supplied rental agreements, asks a pretrained local language model for six fields, validates its JSON, and compares predictions with the provided labels.

## What the assignment requires

The required output columns are `Aggrement Value`, `Aggrement Start Date`, `Aggrement End Date`, `Renewal Notice (Days)`, `Party One`, and `Party Two`. The supplied CSV spells “Agreement” as “Aggrement”; the project preserves that exact spelling in exported files. See [docs/requirements_checklist.md](docs/requirements_checklist.md) for the data audit and known label issues.

## How the project works

```text
DOCX / PNG -> text reader / OCR -> local Ollama model -> six-field JSON
           -> validated predictions.csv -> field-level evaluation report
```

`src/read_documents.py` reads Word documents and uses Tesseract OCR for scanned PNG, JPG/JPEG, TIFF, or BMP images. `src/semantic_extractor.py` sends the extracted text to Ollama on this computer (`localhost`), not to a cloud AI provider. It validates model output against the six-field schema. `src/app.py` provides a local upload screen for one DOCX or scanned image at a time. `src/extract_test_set.py` processes the labeled test set. `src/evaluate.py` compares generated predictions with the supplied test labels.

Field extraction is semantic: the language model reads the agreement text rather than relying on fixed page positions, regular expressions, or template-specific field rules. OCR only turns image pixels into text. The evaluator has format normalization for scoring; it does not extract fields from agreements.

## Setup on Windows

You have already installed Ollama and downloaded `qwen3:4b`. The image reader also needs Tesseract OCR installed and available to `pytesseract`. Python dependencies are listed in `requirements.txt`.

Open PowerShell in this project folder and install Python dependencies if needed:

```powershell
python -m pip install -r requirements.txt
```

Make sure the Ollama app is running. To confirm the model is installed, run:

```powershell
ollama list
```

## Run the project

First, read the test documents and report their extracted text lengths:

```powershell
python src\read_documents.py data\test
```

Generate predictions for all four labeled test documents:

```powershell
python src\extract_test_set.py --refresh
```

`--refresh` asks the model to run again for every test document. Without it, the program reuses saved JSON results when available. Model processing can take several minutes per document.

Evaluate the saved predictions:

```powershell
python src\evaluate.py
```

Run the project checks:

```powershell
python -m unittest discover -s tests -v
```

## Interactive Streamlit Web Interface

From PowerShell in the project folder, start the interactive interface:

```powershell
streamlit run src\app.py
```

### UI Features
- **Document Ingestion**: Upload DOCX contracts or scanned images (PNG, JPG, JPEG, TIFF, BMP up to 25 MB), or choose directly from sample benchmark agreements.
- **System Health Monitor**: Live sidebar status checks for Ollama (`qwen3:4b`) and Tesseract OCR engine with automated troubleshooting instructions.
- **Multi-Phase Progress Tracking**: Step-by-step visual indicators tracking document parsing, local model querying, and schema validation.
- **Structured Results Table**: Clean card and table views displaying all six required fields with color-coded status badges (`Extracted` vs `Null / Not Specified`).
- **Source Evidence Grounding**: Extracts authentic supporting context quotes directly from the contract text without hallucinating.
- **Missing-Value Transparency**: Clear amber badges and diagnostic notes for fields that are absent in the agreement.
- **Dual Export**: One-click downloads for official assignment CSV (`File Name,Aggrement Value,...`) and rich JSON with full metadata and evidence quotes.


## RESTful Web Service (FastAPI)

A production-ready RESTful API service is provided in `src/api.py`. It wraps the entire document parsing, local AI extraction, and evidence grounding pipeline.

### Start the API Server

From PowerShell in the project root:

```powershell
python -m uvicorn src.api:app --host 0.0.0.0 --port 8000
```

### Interactive API Documentation
- **Swagger UI**: Open `http://localhost:8000/docs` in your browser to interactively test file uploads.
- **ReDoc**: Accessible at `http://localhost:8000/redoc`.

### API Endpoints
- `GET /health`: Health checks verifying local Ollama (`qwen3:4b`) and Tesseract OCR availability.
- `POST /extract`: Ingests a DOCX or scanned image file (multipart/form-data) and returns the extracted 6 fields with grounded source evidence in JSON.
- `GET /metrics`: Returns the latest test set evaluation recall scores.

#### Example Extraction Request (PowerShell / curl):
```powershell
curl.exe -F "file=@data\test\156155545-Rental-Agreement-Kns-Home.pdf.docx" http://localhost:8000/extract
```


## Evaluation and current status

The latest available predictions were evaluated against 4 test labels. Recall compares normalized values; raw exact accuracy requires the strings to be identical. Measured recall is:

| Field | Matches / labeled | Recall |
|---|---:|---:|
| Agreement Value | 4 / 4 | 100% |
| Agreement Start Date | 3 / 4 | 75% |
| Agreement End Date | 2 / 4 | 50% |
| Renewal Notice (Days) | 2 / 4 | 50% |
| Party One | 2 / 4 | 50% |
| Party Two | 2 / 4 | 50% |

All 10 unit tests pass. Name scoring treats punctuation, case, whitespace, and adjacent single-letter initials consistently; it still requires exact normalized tokens and does not use fuzzy or substring matching. This raised Party Two recall from 0/4 to 2/4 without changing model predictions. Date and amount normalization reject invalid or ambiguous values rather than silently guessing. A duplicate `options` entry in the Ollama request was fixed so deterministic temperature and the response limit are both sent.

The latest prompt asks for short contracting-party names and cross-checks an amount written in digits against the same amount in words. These are the latest reported predictions. Start/end dates and party names should still be checked against the agreement because the sample is small and the model can make mistakes.

These are diagnostic results on only four documents, and one document ID occurs in both train and test labels. They do not establish generalization. See `outputs/field_recall_report.csv` and `outputs/evaluation_summary.txt` for generated metrics. Original documents and CSVs remain unchanged.

## Privacy and limitations

Document text may include personal details. OCR and model requests run locally on this computer through Tesseract and Ollama. Do not paste agreement text into public services. Model answers can still be wrong; review extracted fields against the agreement before using them. Null means the model did not return a value; it does not prove that the agreement lacks that information.

The supplied test set is very small and has a train/test overlap. Some labels are blank or malformed, so the evaluator excludes missing labels and reports invalid ones separately. The project preserves source values and uses conservative normalization only for metric comparison.

## Interview explanation

“I separated document reading from semantic extraction. Tesseract only turns scanned images into text; a pretrained model identifies the agreement fields. I validate the model’s JSON against a fixed schema, preserve missing facts as null, and report field-level recall using transparent normalization. The model runs locally to keep document text on the machine. The small and imperfect labels limit what the evaluation can prove.”
