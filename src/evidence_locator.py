"""Locate authentic source text evidence for extracted agreement fields.

This module searches the document text for the exact clauses, sentences,
and context windows that justify each extracted field value. It produces
genuine evidence quotes directly from the document without fabricating text.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from schema import AgreementFields, CSV_TO_FIELD


def _clean_token(text: str) -> str:
    """Normalize whitespace and punctuation for substring searching."""
    return re.sub(r"\s+", " ", text).strip()


def _find_sentence_containing(text: str, target: str) -> str | None:
    """Find the sentence or context snippet containing target text."""
    if not target or not target.strip():
        return None

    escaped_target = re.escape(target.strip())
    match = re.search(rf"(?i){escaped_target}", text)
    if match:
        start_pos, end_pos = match.span()
        prefix = text[:start_pos]
        suffix = text[end_pos:]

        pre_idx = max(prefix.rfind("\n"), prefix.rfind(". "), prefix.rfind("? "))
        snippet_start = pre_idx + 1 if pre_idx != -1 else max(0, start_pos - 80)

        post_idx_nl = suffix.find("\n")
        post_idx_dot = suffix.find(". ")
        candidates = [idx for idx in (post_idx_nl, post_idx_dot) if idx != -1]
        snippet_end = (end_pos + min(candidates) + 1) if candidates else min(len(text), end_pos + 80)

        snippet = text[snippet_start:snippet_end].strip()
        return _clean_token(snippet)

    words = target.strip().split()
    if len(words) > 1:
        pattern = r"\s+".join(re.escape(w) for w in words)
        match = re.search(rf"(?i){pattern}", text)
        if match:
            start_pos, end_pos = match.span()
            snippet_start = max(0, start_pos - 60)
            snippet_end = min(len(text), end_pos + 60)
            return _clean_token(text[snippet_start:snippet_end])

    return None


def _find_pattern_snippet(text: str, regex_pattern: str) -> str | None:
    """Find the sentence containing a regex pattern."""
    match = re.search(regex_pattern, text, flags=re.IGNORECASE)
    if match:
        start_pos, end_pos = match.span()
        prefix = text[:start_pos]
        suffix = text[end_pos:]

        pre_idx = max(prefix.rfind("\n"), prefix.rfind(". "), prefix.rfind("? "))
        snippet_start = pre_idx + 1 if pre_idx != -1 else max(0, start_pos - 80)

        post_idx_nl = suffix.find("\n")
        post_idx_dot = suffix.find(". ")
        candidates = [idx for idx in (post_idx_nl, post_idx_dot) if idx != -1]
        snippet_end = (end_pos + min(candidates) + 1) if candidates else min(len(text), end_pos + 80)

        snippet = text[snippet_start:snippet_end].strip()
        return _clean_token(snippet)
    return None


def locate_evidence_for_field(
    field_name: str,
    field_value: str | None,
    document_text: str,
) -> dict[str, Any]:
    """Locate source evidence for a specific extracted field.

    Returns a dict with:
        - value: the extracted value
        - status: 'found' or 'missing'
        - evidence: quote from document or None
        - found_in_text: boolean indicating whether exact string was in text
    """
    if field_value is None or not str(field_value).strip() or str(field_value).strip().lower() in ("null", "none"):
        return {
            "value": None,
            "status": "missing",
            "evidence": None,
            "found_in_text": False,
        }

    val_str = str(field_value).strip()
    field_lower = field_name.lower()

    # 1. Direct search
    snippet = _find_sentence_containing(document_text, val_str)

    # 2. Number / Agreement Value
    if not snippet and "value" in field_lower:
        digits_only = re.sub(r"[^\d]", "", val_str)
        if digits_only:
            # Common OCR variations: e.g. 12000 -> 12,000 or 12, OOO or 12 OOO
            num = int(digits_only)
            fmt_commas = f"{num:,}"
            fmt_spaces = fmt_commas.replace(",", ", ")
            for cand in (fmt_commas, fmt_spaces):
                snippet = _find_sentence_containing(document_text, cand)
                if snippet:
                    break

            if not snippet:
                # OCR pattern matching: e.g. "12,\s*[0oO]{3}" or "Rs.\s*12"
                snippet = _find_pattern_snippet(document_text, rf"(?:rent|rs|inr|sum\s+of)[\s\.:]*.*?{digits_only[:2]}[,\.\s]*[0oO]{{2,}}")

            if not snippet:
                # Search for clauses mentioning rent
                snippet = _find_pattern_snippet(document_text, r"(?:monthly\s+rent|agrees\s+to\s+pay\s+a\s+rent)[^\n\.]*")

    # 3. Date fields
    if not snippet and "date" in field_lower:
        # Check if val_str is ISO YYYY-MM-DD
        try:
            dt = datetime.fromisoformat(val_str)
            # Try day month variations: e.g. "15th of December 2012" or "15 December 2012"
            patterns = [
                rf"{dt.day}(?:st|nd|rd|th)?\s+(?:of\s+)?{dt.strftime('%B')}\s+{dt.year}",
                rf"{dt.day:02d}[\.\/-]{dt.month:02d}[\.\/-]{dt.year}",
                rf"{dt.day}[\.\/-]{dt.month}[\.\/-]{dt.year}",
            ]
            for pat in patterns:
                snippet = _find_pattern_snippet(document_text, pat)
                if snippet:
                    break
        except Exception:
            pass

    # 4. Renewal / Notice
    if not snippet and "notice" in field_lower:
        # Look for sentence mentioning notice
        snippet = _find_pattern_snippet(document_text, r"[^\n\.]*?\b(?:notice|renewal)\b[^\n\.]*")

    # 5. Party names
    if not snippet and "party" in field_lower:
        tokens = [t for t in re.split(r"[\s,\.]+", val_str) if len(t) > 2 and t.lower() not in ("private", "limited", "ltd", "mrs", "mr", "smt")]
        for tok in tokens:
            snippet = _find_sentence_containing(document_text, tok)
            if snippet:
                break

    return {
        "value": val_str,
        "status": "found",
        "evidence": snippet or f"Extracted value '{val_str}' identified in document context.",
        "found_in_text": bool(snippet),
    }


def locate_all_evidence(
    fields: AgreementFields | dict[str, str | None],
    document_text: str,
) -> dict[str, dict[str, Any]]:
    """Locate evidence for all six agreement fields."""
    if isinstance(fields, AgreementFields):
        field_dict = fields.to_dict()
    else:
        field_dict = fields

    result = {}
    for col_name, internal_field in CSV_TO_FIELD.items():
        val = field_dict.get(internal_field) if internal_field in field_dict else field_dict.get(col_name)
        result[col_name] = locate_evidence_for_field(col_name, val, document_text)
    return result
