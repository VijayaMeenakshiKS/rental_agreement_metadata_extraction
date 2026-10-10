"""Evaluate test predictions against labels with documented normalization."""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
GROUND_TRUTH_CSV = DATA_DIR / "test.csv"
PREDICTIONS_CSV = OUTPUT_DIR / "predictions.csv"
REPORT_CSV = OUTPUT_DIR / "field_recall_report.csv"
SUMMARY_TXT = OUTPUT_DIR / "evaluation_summary.txt"
ID_COLUMN = "File Name"
FIELDS = [
    "Aggrement Value",
    "Aggrement Start Date",
    "Aggrement End Date",
    "Renewal Notice (Days)",
    "Party One",
    "Party Two",
]
DATE_FORMATS = (
    "%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y",
    "%d-%m-%Y", "%d-%m-%y", "%d %B %Y", "%B %d %Y", "%B %d, %Y",
    "%d %b %Y", "%b %d %Y", "%b %d, %Y",
)
MISSING_MARKERS = {"", "null", "none", "n/a", "na"}


def present(value: object) -> bool:
    return str(value if value is not None else "").strip().casefold() not in MISSING_MARKERS


def normalize_text(value: str) -> str:
    """Ignore capitalization and repeated/leading/trailing whitespace only."""
    return " ".join(value.split()).casefold()


def normalize_name(value: str) -> str:
    """Normalize punctuation and equivalent adjacent initial spellings.

    For example, ``A.B. Smith`` and ``AB Smith`` normalize identically. This
    remains exact token matching after a documented name-format conversion;
    it does not use fuzzy similarity or substring matching.
    """
    tokens = re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE)
    # The regex above intentionally does not retain punctuation. Join adjacent
    # one-letter tokens so dotted and spaced initials compare consistently.
    normalized: list[str] = []
    index = 0
    while index < len(tokens):
        if len(tokens[index]) == 1 and tokens[index].isalpha():
            initials = []
            while index < len(tokens) and len(tokens[index]) == 1 and tokens[index].isalpha():
                initials.append(tokens[index])
                index += 1
            normalized.append("".join(initials))
        else:
            normalized.append(tokens[index])
            index += 1
    return " ".join(normalized)


def normalize_date(value: str) -> str | None:
    candidate = re.sub(r"(?<=\d)\*", "", value.strip())
    candidate = re.sub(r"\bof\b", " ", candidate, flags=re.IGNORECASE)
    candidate = candidate.replace(",", " ")
    words = candidate.split()
    for index, word in enumerate(words):
        lower = word.casefold()
        for ordinal in ("st", "nd", "rd", "th"):
            if lower.endswith(ordinal) and lower[: -len(ordinal)].isdigit():
                words[index] = word[: -len(ordinal)]
                break
    candidate = " ".join(words)
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(candidate, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_money_number(candidate: str) -> Decimal | None:
    candidate = candidate.replace(" ", "")
    # Require complete thousands groups. Without this check, OCR text such as
    # "12, OOO" could be reduced to 12 and falsely counted as a money match.
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", candidate):
        return None
    try:
        return Decimal(candidate.replace(",", ""))
    except InvalidOperation:
        return None


def normalize_money(value: str) -> Decimal | None:
    candidate = value.strip().casefold()
    for prefix in ("inr", "rs.", "rs", "₹", "$", "€", "£"):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :].strip()
            break
    for suffix in ("/-", " rupees", " rupee", " per month", "/month", " monthly"):
        if candidate.endswith(suffix):
            candidate = candidate[: -len(suffix)].strip()
            break
    parsed = _parse_money_number(candidate)
    if parsed is not None:
        return parsed

    # A single numeric amount in explanatory text is still comparable. If the
    # model returns multiple numbers, refuse to guess which one is the value.
    number_tokens: list[str] = []
    current = ""
    for character in value:
        if character.isdigit() or (character in ",." and current):
            current += character
        elif current:
            number_tokens.append(current)
            current = ""
    if current:
        number_tokens.append(current)
    if len(number_tokens) == 1:
        return _parse_money_number(number_tokens[0])
    return None


def normalize_days(value: str) -> int | None:
    candidate = value.strip().casefold()
    for suffix in (" days", " day", "days", "day"):
        if candidate.endswith(suffix):
            candidate = candidate[: -len(suffix)].strip()
            break
    try:
        return int(candidate)
    except ValueError:
        return None


def normalize(field: str, value: str) -> object | None:
    if not present(value):
        return None
    if field in {"Aggrement Start Date", "Aggrement End Date"}:
        return normalize_date(value)
    if field == "Aggrement Value":
        return normalize_money(value)
    if field == "Renewal Notice (Days)":
        return normalize_days(value)
    if field in {"Party One", "Party Two"}:
        return normalize_name(value)
    return normalize_text(value)


def calculate_field_metrics(
    field: str,
    truth_by_id: dict[str, dict[str, str]],
    prediction_by_id: dict[str, dict[str, str]],
) -> dict[str, int | str]:
    """Calculate normalized recall and strict raw exact accuracy for one field."""
    labeled = invalid_ground_truth = matched = raw_exact = 0
    for identifier, truth in truth_by_id.items():
        expected = truth.get(field, "")
        if not present(expected):
            continue
        normalized_expected = normalize(field, expected)
        if normalized_expected is None:
            invalid_ground_truth += 1
            continue
        labeled += 1
        prediction = prediction_by_id.get(identifier, {}).get(field, "")
        if prediction == expected:
            raw_exact += 1
        normalized_prediction = normalize(field, prediction)
        if normalized_prediction is not None and normalized_prediction == normalized_expected:
            matched += 1
    recall = f"{(100 * matched / labeled):.2f}" if labeled else "unavailable"
    exact_accuracy = f"{(100 * raw_exact / labeled):.2f}" if labeled else "unavailable"
    return {
        "field": field,
        "labeled_count": labeled,
        "invalid_ground_truth_count": invalid_ground_truth,
        "normalized_matches": matched,
        "recall_percent": recall,
        "raw_exact_matches": raw_exact,
        "raw_exact_accuracy_percent": exact_accuracy,
    }


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))


def main() -> None:
    if not GROUND_TRUTH_CSV.exists():
        raise SystemExit(f"Ground truth file not found: {GROUND_TRUTH_CSV}")
    if not PREDICTIONS_CSV.exists():
        raise SystemExit(
            f"Predictions not found: {PREDICTIONS_CSV}. Run src\\extract_test_set.py first."
        )

    truth_rows = read_rows(GROUND_TRUTH_CSV)
    prediction_rows = read_rows(PREDICTIONS_CSV)
    truth_by_id = {row.get(ID_COLUMN, ""): row for row in truth_rows}
    prediction_by_id = {row.get(ID_COLUMN, ""): row for row in prediction_rows}
    if len(truth_by_id) != len(truth_rows) or len(prediction_by_id) != len(prediction_rows):
        raise SystemExit("Duplicate document IDs found in the test labels or predictions.")

    results = [calculate_field_metrics(field, truth_by_id, prediction_by_id) for field in FIELDS]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    columns = [
        "field",
        "labeled_count",
        "invalid_ground_truth_count",
        "normalized_matches",
        "recall_percent",
        "raw_exact_matches",
        "raw_exact_accuracy_percent",
    ]
    with REPORT_CSV.open("w", newline="", encoding="utf-8-sig") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(results)

    train_ids = {row.get(ID_COLUMN, "") for row in read_rows(DATA_DIR / "train.csv")}
    overlap_count = len(train_ids & set(truth_by_id))
    missing_prediction_count = len(set(truth_by_id) - set(prediction_by_id))
    extra_prediction_count = len(set(prediction_by_id) - set(truth_by_id))
    summary_lines = [
        f"Ground-truth test rows: {len(truth_rows)}",
        f"Prediction rows: {len(prediction_rows)}",
        f"Test rows without predictions: {missing_prediction_count}",
        f"Predictions without test labels: {extra_prediction_count}",
        f"Train/test ID overlap: {overlap_count}",
        "",
        "Normalization: names ignore case, punctuation, whitespace, and equivalent adjacent single-letter initials; name comparison remains exact after normalization (no fuzzy or substring matching). Dates accept dotted, slash, hyphen, ISO, and common written-month forms; amounts compare as validated decimals; notice periods compare as integer days.",
        "Recall denominator: non-empty, valid ground-truth values. Invalid labels are counted separately. A missing prediction is a miss.",
        "Raw exact accuracy requires the prediction string to equal the ground-truth string exactly.",
        "",
    ]
    for result in results:
        summary_lines.append(
            f"{result['field']}: recall {result['recall_percent']}% "
            f"({result['normalized_matches']}/{result['labeled_count']}), "
            f"raw exact accuracy {result['raw_exact_accuracy_percent']}% "
            f"({result['raw_exact_matches']}/{result['labeled_count']}), "
            f"invalid labels {result['invalid_ground_truth_count']}"
        )
    if overlap_count:
        summary_lines.extend(
            ["", "Caution: at least one test document also occurs in train.csv; interpret scores as a small, non-independent check."]
        )
    SUMMARY_TXT.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(
        f"Evaluated {len(prediction_rows)} prediction rows against {len(truth_rows)} labeled test rows."
    )
    if overlap_count:
        print(f"WARNING: {overlap_count} test ID(s) also occur in train.csv; see evaluation summary.")
    for result in results:
        print(
            f"{result['field']}: recall={result['recall_percent']}% "
            f"({result['normalized_matches']}/{result['labeled_count']}), "
            f"raw exact={result['raw_exact_matches']}/{result['labeled_count']}"
        )
    print(f"Saved report to {REPORT_CSV}")
    print(f"Saved explanation to {SUMMARY_TXT}")


if __name__ == "__main__":
    main()

