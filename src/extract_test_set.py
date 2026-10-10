"""Extract every document listed in data/test.csv and build predictions.csv."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from semantic_extractor import OUTPUT_DIR, extract_document
from read_documents import SUPPORTED_SUFFIXES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
TEST_CSV = DATA_DIR / "test.csv"
DOCUMENT_DIR = DATA_DIR / "test"
ID_COLUMN = "File Name"
FIELD_COLUMNS = [
    "Aggrement Value",
    "Aggrement Start Date",
    "Aggrement End Date",
    "Renewal Notice (Days)",
    "Party One",
    "Party Two",
]
OUTPUT_CSV = OUTPUT_DIR / "predictions.csv"


def document_id(path: Path) -> str:
    """Match the assignment IDs, including names that end in .pdf.docx."""
    if path.name.lower().endswith(".pdf.docx"):
        return path.name[: -len(".pdf.docx")]
    return path.stem


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract the labeled test set.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Run the AI again for every test document instead of reusing saved JSON.",
    )
    args = parser.parse_args()

    with TEST_CSV.open("r", newline="", encoding="utf-8-sig") as csv_file:
        test_rows = list(csv.DictReader(csv_file))
    if not test_rows:
        raise SystemExit(f"No test rows found in {TEST_CSV}")

    documents = {
        document_id(path): path
        for path in DOCUMENT_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    }
    output_rows: list[dict[str, str | None]] = []
    for test_row in test_rows:
        identifier = test_row.get(ID_COLUMN, "")
        document = documents.get(identifier)
        if document is None:
            raise SystemExit(f"No test document matches CSV ID: {identifier}")

        prediction_path = OUTPUT_DIR / f"{document.name}.prediction.json"
        if args.refresh or not prediction_path.exists():
            try:
                prediction_path = extract_document(document)
            except (OSError, ValueError, RuntimeError) as exc:
                raise SystemExit(f"Could not process {document.name}: {exc}") from exc

        try:
            prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Could not read saved result for {identifier}: {exc}") from exc

        missing = [column for column in FIELD_COLUMNS if column not in prediction]
        if missing:
            raise SystemExit(
                f"Saved result for {identifier} is missing columns: {', '.join(missing)}"
            )
        invalid = [
            column
            for column in FIELD_COLUMNS
            if prediction[column] is not None and not isinstance(prediction[column], str)
        ]
        if invalid:
            raise SystemExit(
                f"Saved result for {identifier} has non-text values in: {', '.join(invalid)}"
            )
        output_rows.append(
            {
                ID_COLUMN: identifier,
                **{column: prediction[column] for column in FIELD_COLUMNS},
            }
        )
        print(f"Ready: {identifier}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=[ID_COLUMN, *FIELD_COLUMNS])
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"Saved {len(output_rows)} test predictions to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
