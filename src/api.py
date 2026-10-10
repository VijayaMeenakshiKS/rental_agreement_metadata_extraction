"""RESTful API service for Rental Agreement Metadata Extraction.

Exposes endpoints for document metadata extraction, service health checks,
and benchmark metrics using FastAPI and Uvicorn.
"""
from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Add src to sys.path
SOURCE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SOURCE_DIR.parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from evidence_locator import locate_all_evidence
from read_documents import SUPPORTED_SUFFIXES, extract_text
from schema import CSV_TO_FIELD, AgreementFields
from semantic_extractor import DEFAULT_MODEL, extract_fields

app = FastAPI(
    title="Rental Agreement Metadata Extraction API",
    description=(
        "Production-ready AI/ML REST API for template-agnostic metadata extraction "
        "from rental agreements (.docx and scanned images) using local Ollama (qwen3:4b) "
        "and Tesseract OCR."
    ),
    version="1.0.0",
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


class ExtractionResponse(BaseModel):
    document_id: str
    filename: str
    extracted_at: str
    model: str
    character_count: int
    fields: dict[str, str | None]
    evidence: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    ollama_online: bool
    ollama_model_ready: bool
    ollama_message: str
    tesseract_ready: bool
    supported_formats: list[str]


def _check_ollama(model_name: str = DEFAULT_MODEL) -> tuple[bool, bool, str]:
    try:
        req = Request("http://localhost:11434/api/tags", method="GET")
        with urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            is_ready = any(m.startswith(model_name.split(":")[0]) for m in models)
            if is_ready:
                return True, True, f"Ollama online and model '{model_name}' is ready."
            return True, False, f"Ollama online, but model '{model_name}' is not pulled."
    except (URLError, TimeoutError, OSError):
        return False, False, "Cannot connect to Ollama at http://localhost:11434."
    except Exception as exc:
        return False, False, f"Ollama check error: {exc}"


@app.get("/", tags=["Info"])
def root() -> dict[str, Any]:
    """Root endpoint with service metadata and documentation links."""
    return {
        "service": "Rental Agreement Metadata Extraction API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "health_url": "/health",
        "extract_url": "/extract",
        "metrics_url": "/metrics",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health(model: str = Query(DEFAULT_MODEL, description="Ollama model to verify")) -> HealthResponse:
    """Service health check for Ollama API and Tesseract OCR."""
    ollama_online, model_ready, ollama_msg = _check_ollama(model)
    tesseract_ready = shutil.which("tesseract") is not None

    overall = "healthy" if (ollama_online and model_ready) else "degraded"
    return HealthResponse(
        status=overall,
        ollama_online=ollama_online,
        ollama_model_ready=model_ready,
        ollama_message=ollama_msg,
        tesseract_ready=tesseract_ready,
        supported_formats=sorted(list(SUPPORTED_SUFFIXES)),
    )


@app.post("/extract", response_model=ExtractionResponse, tags=["Extraction"])
async def extract_metadata(
    file: UploadFile = File(..., description="DOCX agreement or scanned image (PNG, JPG, TIFF, BMP)"),
    model: str = Query(DEFAULT_MODEL, description="Ollama model to use for extraction"),
) -> ExtractionResponse:
    """Extract six metadata fields and authentic source evidence from an uploaded contract."""
    filename = Path(file.filename or "uploaded_document").name
    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file extension '{extension}'. "
                f"Allowed types: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
            ),
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size limit of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty (0 bytes).",
        )

    # Document ID format
    if filename.lower().endswith(".pdf.docx"):
        doc_id = filename[:-len(".pdf.docx")]
    else:
        doc_id = Path(filename).stem

    try:
        with tempfile.TemporaryDirectory(prefix="api_extract_") as tmp_dir:
            tmp_path = Path(tmp_dir) / filename
            tmp_path.write_bytes(content)

            # 1. Read document text / OCR
            text = extract_text(tmp_path)

            # 2. Extract fields using local LLM
            fields: AgreementFields = extract_fields(text, model=model)

            # 3. Locate source text evidence
            evidence = locate_all_evidence(fields, text)

        return ExtractionResponse(
            document_id=doc_id,
            filename=filename,
            extracted_at=datetime.utcnow().isoformat() + "Z",
            model=model,
            character_count=len(text),
            fields=fields.to_assignment_columns(),
            evidence={k: v.get("evidence") for k, v in evidence.items()},
        )

    except RuntimeError as r_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Model extraction error: {r_err}",
        )
    except ValueError as v_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing error: {v_err}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failure: {exc}",
        )


@app.get("/metrics", tags=["Metrics"])
def get_metrics() -> dict[str, Any]:
    """Return the latest test set per-field recall scores."""
    report_file = PROJECT_ROOT / "outputs" / "field_recall_report.csv"
    if not report_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation metrics report not found. Run python src/evaluate.py first.",
        )

    with open(report_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    return {
        "dataset": "test",
        "sample_count": len(rows),
        "fields": rows,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
