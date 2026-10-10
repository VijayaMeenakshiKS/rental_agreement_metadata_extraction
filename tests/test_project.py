"""Unit tests for schema validation and evaluation normalization."""
import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluate import calculate_field_metrics, normalize, present  # noqa: E402
from schema import AgreementFields, validate_model_result  # noqa: E402


class SchemaTests(unittest.TestCase):
    def test_all_six_fields_are_required(self):
        result = validate_model_result({
            "agreement_value": "12000",
            "agreement_start_date": "01.04.2008",
            "agreement_end_date": "31.03.2009",
            "renewal_notice_days": "60",
            "party_one": "Landlord",
            "party_two": "Tenant",
        })
        self.assertIsInstance(result, AgreementFields)
        self.assertEqual(result.to_assignment_columns()["Aggrement Value"], "12000")

    def test_missing_or_wrong_type_field_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_model_result({"agreement_value": 12000})

    def test_null_is_a_valid_missing_value(self):
        value = {field: None for field in (
            "agreement_value", "agreement_start_date", "agreement_end_date",
            "renewal_notice_days", "party_one", "party_two",
        )}
        self.assertIsNone(validate_model_result(value).party_one)


class NormalizationTests(unittest.TestCase):
    def test_dates_normalize_and_impossible_date_is_invalid(self):
        self.assertEqual(normalize("Aggrement Start Date", "01.04.2008"), "2008-04-01")
        self.assertEqual(normalize("Aggrement Start Date", "1st April 2008"), "2008-04-01")
        self.assertEqual(normalize("Aggrement Start Date", "1-04-08"), "2008-04-01")
        self.assertEqual(normalize("Aggrement Start Date", "15th of December 2012"), "2012-12-15")
        self.assertEqual(normalize("Aggrement Start Date", "1* April 2010"), "2010-04-01")
        self.assertIsNone(normalize("Aggrement End Date", "31.11.2009"))

    def test_money_and_notice_days_normalize(self):
        self.assertEqual(normalize("Aggrement Value", "₹ 12,000"), normalize("Aggrement Value", "12000"))
        self.assertEqual(normalize("Aggrement Value", "Rent amount is INR 12,000 monthly"), normalize("Aggrement Value", "12000"))
        self.assertIsNone(normalize("Aggrement Value", "Rs.12, OOO (Rupees Twelve Thousand only)"))
        self.assertIsNone(normalize("Aggrement Value", "12000 for 12 months"))
        self.assertEqual(normalize("Renewal Notice (Days)", "60 days"), 60)

    def test_names_ignore_case_and_whitespace(self):
        self.assertEqual(normalize("Party One", "  A   Person "), normalize("Party One", "a person"))

    def test_name_initial_punctuation_is_normalized_exactly(self):
        self.assertEqual(
            normalize("Party Two", "A.B. Smith"),
            normalize("Party Two", "AB Smith"),
        )

    def test_missing_values_are_not_counted_as_present(self):
        self.assertFalse(present("  "))
        self.assertFalse(present("null"))
        self.assertTrue(present("0"))


class MetricTests(unittest.TestCase):
    def test_recall_uses_labeled_denominator_and_normalized_match(self):
        truth = {
            "a": {"Party One": "Alice"},
            "b": {"Party One": ""},
            "c": {"Party One": "Bob"},
        }
        predictions = {
            "a": {"Party One": " ALICE "},
            "c": {"Party One": "Wrong"},
        }
        result = calculate_field_metrics("Party One", truth, predictions)
        self.assertEqual(result["labeled_count"], 2)
        self.assertEqual(result["normalized_matches"], 1)
        self.assertEqual(result["recall_percent"], "50.00")
        self.assertEqual(result["raw_exact_matches"], 0)

    def test_invalid_ground_truth_is_excluded_from_recall(self):
        truth = {"a": {"Aggrement End Date": "31.11.2009"}}
        result = calculate_field_metrics("Aggrement End Date", truth, {})
        self.assertEqual(result["labeled_count"], 0)
        self.assertEqual(result["invalid_ground_truth_count"], 1)
        self.assertEqual(result["recall_percent"], "unavailable")


class EvidenceTests(unittest.TestCase):
    def test_locate_evidence_found_and_missing(self):
        from evidence_locator import locate_evidence_for_field, locate_all_evidence

        text = "The monthly rent is Rs. 15,000 payable by tenant John Doe."
        res_val = locate_evidence_for_field("Aggrement Value", "15000", text)
        self.assertTrue(res_val["found_in_text"])
        self.assertEqual(res_val["status"], "found")

        res_miss = locate_evidence_for_field("Renewal Notice (Days)", None, text)
        self.assertFalse(res_miss["found_in_text"])
        self.assertEqual(res_miss["status"], "missing")
        self.assertIsNone(res_miss["evidence"])


class ApiTests(unittest.TestCase):
    def test_root_endpoint_direct(self):
        from api import root

        data = root()
        self.assertIn("service", data)
        self.assertEqual(data["version"], "1.0.0")

    def test_health_endpoint_direct(self):
        from api import health

        res = health()
        self.assertIn(res.status, ("healthy", "degraded"))
        self.assertIn(".docx", res.supported_formats)

    def test_metrics_endpoint_direct(self):
        from api import get_metrics

        data = get_metrics()
        self.assertEqual(data["dataset"], "test")
        self.assertGreaterEqual(data["sample_count"], 1)


if __name__ == "__main__":
    unittest.main()



