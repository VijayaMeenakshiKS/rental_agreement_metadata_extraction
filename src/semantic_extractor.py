"""Run semantic extraction through a local Ollama model.

Agreement text is sent only to Ollama on this computer (localhost). No cloud
provider or API key is used by this module.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from extraction_prompt import SYSTEM_INSTRUCTIONS, make_user_message
from read_documents import extract_text
from schema import AgreementFields, json_schema, validate_model_result

LOCAL_CHAT_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen3:4b"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"


def extract_fields(agreement_text: str, model: str | None = None) -> AgreementFields:
    """Ask the local model for six fields and validate its JSON response."""
    selected_model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": make_user_message(agreement_text)},
        ],
        "format": json_schema(),
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "num_predict": 512,
            "num_ctx": 4096,
            "num_thread": 6,
        },
    }
    request = Request(
        LOCAL_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=900) as response:
            api_result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(
                f"Model '{selected_model}' is not available. In PowerShell, run "
                f"'ollama pull {selected_model}' and try again."
            ) from exc
        raise RuntimeError(
            f"Ollama returned HTTP {exc.code}. Check that Ollama is running, "
            "then try again."
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            "Could not reach Ollama at localhost:11434. Install and open Ollama, "
            "then make sure the selected model is downloaded."
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            "The local model did not respond within 15 minutes. Try again after "
            "closing other heavy apps, or use a smaller model."
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Ollama returned an unreadable response.") from exc

    try:
        content = api_result["message"]["content"]
        model_result = json.loads(content)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("The model did not return valid structured JSON.") from exc
    return validate_model_result(model_result)


def extract_document(path: Path) -> Path:
    """Read one agreement, extract its fields, and save local JSON output."""
    text = extract_text(path)
    fields = extract_fields(text)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{path.name}.prediction.json"
    filename = path.name
    if filename.lower().endswith(".pdf.docx"):
        document_id = filename[:-len(".pdf.docx")]
    else:
        document_id = path.stem
    prediction = {
        "document_id": document_id,
        **fields.to_assignment_columns(),
    }
    output_path.write_text(
        json.dumps(prediction, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract rental agreement fields with a local Ollama model."
    )
    parser.add_argument(
        "document", type=Path, help="A DOCX or supported scanned image agreement"
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Local Ollama model (default: {DEFAULT_MODEL})",
    )
    args = parser.parse_args()
    try:
        output_path = extract_document(args.document)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Saved prediction JSON to {output_path}")


if __name__ == "__main__":
    main()




