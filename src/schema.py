"""The answer form shared by extraction, CSV export, and evaluation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

# Internal Python names map to the assignment's exact CSV labels.
# The source CSV misspells "Agreement" as "Aggrement"; keep that spelling
# at the export boundary so output matches the supplied assignment files.
CSV_TO_FIELD = {
    "Aggrement Value": "agreement_value",
    "Aggrement Start Date": "agreement_start_date",
    "Aggrement End Date": "agreement_end_date",
    "Renewal Notice (Days)": "renewal_notice_days",
    "Party One": "party_one",
    "Party Two": "party_two",
}


@dataclass
class AgreementFields:
    """Extracted values; None means the agreement does not support an answer."""

    agreement_value: str | None = None
    agreement_start_date: str | None = None
    agreement_end_date: str | None = None
    renewal_notice_days: str | None = None
    party_one: str | None = None
    party_two: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)

    def to_assignment_columns(self) -> dict[str, str | None]:
        """Return values using the column names supplied in the assignment CSV."""
        values = self.to_dict()
        return {csv_name: values[field] for csv_name, field in CSV_TO_FIELD.items()}


def validate_model_result(value: Any) -> AgreementFields:
    """Reject malformed model output instead of quietly inventing missing data."""
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object containing the six extraction fields.")

    expected = set(CSV_TO_FIELD.values())
    received = set(value)
    if received != expected:
        missing = sorted(expected - received)
        extra = sorted(received - expected)
        details = []
        if missing:
            details.append("missing fields: " + ", ".join(missing))
        if extra:
            details.append("unexpected fields: " + ", ".join(extra))
        raise ValueError("Invalid extraction schema (" + "; ".join(details) + ").")

    cleaned = {}
    for field, field_value in value.items():
        if field_value is not None and not isinstance(field_value, str):
            raise ValueError(f"Field {field!r} must be text or null.")
        if isinstance(field_value, str) and field_value.strip().lower() in ("null", "none"):
            cleaned[field] = None
        else:
            cleaned[field] = field_value
    return AgreementFields(**cleaned)


def json_schema() -> dict[str, Any]:
    """A provider-neutral JSON Schema for APIs that support structured output."""
    descriptions = {
        "agreement_value": "Only the stated rent/agreement amount; do not substitute a deposit or fee; preserve currency. Verify digits against amount-in-words when both are present; return null if they conflict.",
        "agreement_start_date": "Only the explicit start of the tenancy term, not the signing date; preserve format.",
        "agreement_end_date": "Only the explicit end of the tenancy term; preserve format.",
        "renewal_notice_days": "Only an explicit renewal or non-renewal notice period stated in days; do not convert months.",
        "party_one": "Only the first contracting person's name or company's legal name; omit address, age, parentage, and role description.",
        "party_two": "Only the second contracting person's name or company's legal name; omit address, age, parentage, and role description.",
    }
    return {
        "type": "object",
        "properties": {
            field: {"type": ["string", "null"], "description": description}
            for field, description in descriptions.items()
        },
        "required": list(descriptions),
        "additionalProperties": False,
    }


if __name__ == "__main__":
    print(json.dumps(json_schema(), indent=2))

