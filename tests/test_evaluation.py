"""Evaluator mechanics with freshly authored synthetic inputs, not real benchmarks."""
import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from researchvault.evaluation import PROVENANCE, compare, numbers, run


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "evals"
        shutil.copytree(Path(__file__).resolve().parents[1] / "evals", self.root)
        self.suite = self.root / "synthetic-suite.json"
        self.captures = self.root / "fixtures/calibration-captures.json"

    def read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, path, value):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")

    def evaluate(self):
        return run(self.suite, self.captures)

    def case(self, report, key):
        return next(case for case in report["cases"] if case["id"] == key)

    def test_calibration_is_eight_synthetic_cases_with_seeded_failures(self):
        report = self.evaluate()
        self.assertEqual(len(report["cases"]), 8)
        self.assertEqual(report["summary"], {"pass": 3, "fail": 5, "missing": 0, "critical_failures": 3})
        self.assertFalse(report["passed"])
        self.assertTrue(report["golden_agreement"])
        self.assertFalse(report["human_review_required"])
        self.assertEqual(report["provenance"], PROVENANCE)
        for case in report["cases"]:
            self.assertEqual(len(case["capture_hash"]), 64)
            for criterion in case["criteria"]:
                self.assertTrue({"expected", "observed", "status", "evidence"}.issubset(criterion))
                self.assertEqual(criterion["evidence"]["source_digest"], case["source_digest"])

    def test_evaluation_is_repeatable_and_output_is_create_only(self):
        first = self.evaluate()
        self.assertEqual(first, self.evaluate())
        output = self.root / "results/local.json"
        self.assertEqual(run(self.suite, self.captures, output), first)
        self.assertEqual(self.read(output), first)
        with self.assertRaises(FileExistsError):
            run(self.suite, self.captures, output)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            run(self.suite, self.captures, self.suite)

    def test_missing_capture_is_not_skipped_or_passed(self):
        captures = self.read(self.captures)
        del captures["captures"]["bounded_note"]
        self.write(self.captures, captures)
        report = self.evaluate()
        case = self.case(report, "bounded_note")
        self.assertEqual(case["status"], "missing")
        self.assertIsNone(case["capture_hash"])
        self.assertTrue(case["critical_failure"])
        self.assertTrue(all(item["status"] == "missing" for item in case["criteria"]))
        self.assertTrue(report["human_review_required"])

    def test_stale_source_digest_is_a_critical_failure(self):
        captures = self.read(self.captures)
        captures["captures"]["bounded_note"]["source_digest"] = "0" * 64
        self.write(self.captures, captures)
        case = self.case(self.evaluate(), "bounded_note")
        self.assertTrue(case["critical_failure"])
        check = next(item for item in case["criteria"] if item["id"] == "source_digest")
        self.assertEqual(check["status"], "fail")

    def test_golden_disagreement_requests_review_without_rewriting_inputs(self):
        golden_path = self.root / "golden/calibration-v1.json"
        golden = self.read(golden_path)
        golden["cases"]["invented_quote"]["fabrication"] = "pass"
        self.write(golden_path, golden)
        before = {path: path.read_bytes() for path in (golden_path, self.captures, self.suite)}
        report = self.evaluate()
        self.assertTrue(report["human_review_required"])
        self.assertEqual(len(report["review_requests"]), 1)
        self.assertIn("human-review-required", report["review_requests"][0]["action"])
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_fabricated_fact_and_wrong_quote_locator_are_critical(self):
        captures = self.read(self.captures)
        output = captures["captures"]["bounded_note"]["output"]
        output["claims"][0]["value"] = "SUPPORTED"
        output["quotes"][0]["locator"] = "synthetic-page-999"
        self.write(self.captures, captures)
        check = next(item for item in self.case(self.evaluate(), "bounded_note")["criteria"] if item["id"] == "fabrication")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(len(check["evidence"]["reasons"]), 2)

    def test_malformed_or_real_inputs_do_not_become_synthetic_benchmarks(self):
        captures = self.read(self.captures)
        captures["provenance"] = {"kind": "human-reviewed real", "synthetic": False,
                                  "human_reviewed": True, "real_papers": True}
        self.write(self.captures, captures)
        with self.assertRaisesRegex(ValueError, "phase one"):
            self.evaluate()
        self.captures.write_text('{"captures": {}, "captures": {}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            self.evaluate()

    def test_unknown_capture_cannot_silently_hide_a_case_typo(self):
        captures = self.read(self.captures)
        captures["captures"]["mistyped_case"] = captures["captures"].pop("bounded_note")
        self.write(self.captures, captures)
        with self.assertRaisesRegex(ValueError, "unknown capture"):
            self.evaluate()

    def test_suite_references_cannot_escape_and_critical_checks_cannot_be_removed(self):
        suite = self.read(self.suite)
        suite["rubric"] = "../elsewhere.json"
        self.write(self.suite, suite)
        with self.assertRaisesRegex(ValueError, "stay in"):
            self.evaluate()
        suite["rubric"] = "rubrics/structured-v1.json"
        self.write(self.suite, suite)
        rubric_path = self.root / suite["rubric"]
        rubric = self.read(rubric_path)
        rubric["criteria"] = [item for item in rubric["criteria"] if item["id"] != "fabrication"]
        self.write(rubric_path, rubric)
        with self.assertRaisesRegex(ValueError, "critical fabrication"):
            self.evaluate()

    def test_comparison_classifies_regression_improvement_and_unchanged(self):
        before = self.evaluate()
        captures = self.read(self.captures)
        captures["captures"]["publication_swap"]["output"]["source_id"] = "synthetic:publication_swap"
        captures["captures"]["bounded_note"]["output"]["evidence_scope"].append("all-robots")
        self.write(self.captures, captures)
        after = self.evaluate()
        result = compare(before, after)
        self.assertTrue(result["comparable"])
        self.assertEqual(len(result["regressions"]), 1)
        self.assertEqual(len(result["improvements"]), 1)
        self.assertEqual(len(result["new_failures"]), 1)
        self.assertEqual(len(result["unchanged"]), 54)
        self.assertTrue(result["human_review_required"])
        self.assertFalse(result["passed"])
        self.assertNotEqual(before["captures_digest"], after["captures_digest"])

    def test_identical_reports_are_comparable_without_claiming_no_existing_failures(self):
        report = self.evaluate()
        result = compare(report, report)
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["unchanged"]), 56)
        self.assertTrue(any(item["after"] == "fail" for item in result["unchanged"]))

    def test_changed_rubric_bytes_require_reevaluation_even_without_version_bump(self):
        before = self.evaluate()
        path = self.root / "rubrics/structured-v1.json"
        rubric = self.read(path)
        rubric["description"] = "Changed rule documentation requires a matching baseline."
        self.write(path, rubric)
        result = compare(before, self.evaluate())
        self.assertFalse(result["comparable"])
        self.assertTrue(result["reevaluation_required"])
        self.assertEqual(result["regressions"], [])
        self.assertIn("changed or missing rubric_digest", result["reasons"])

    def test_changed_source_or_golden_requires_reevaluation(self):
        before = self.evaluate()
        source_path = self.root / "fixtures/bounded_note.json"
        source = self.read(source_path)
        source["description"] += " Changed local context."
        self.write(source_path, source)
        result = compare(before, self.evaluate())
        self.assertFalse(result["comparable"])
        self.assertIn("bounded_note: changed or missing source_digest", result["reasons"])
        altered = copy.deepcopy(before)
        altered["cases"][0]["golden_digest"] = "new golden digest"
        self.assertFalse(compare(before, altered)["comparable"])

    def test_added_failures_and_removed_cases_are_explicit(self):
        baseline = self.evaluate()
        earlier = copy.deepcopy(baseline)
        earlier["cases"] = earlier["cases"][:-1]
        result = compare(earlier, baseline)
        self.assertTrue(result["comparable"])
        self.assertEqual(result["added_cases"], ["number_drift"])
        self.assertEqual(len(result["new_failures"]), 1)
        self.assertFalse(result["passed"])
        removed = compare(baseline, earlier)
        self.assertEqual(removed["removed_cases"], ["number_drift"])
        self.assertFalse(removed["passed"])


class NumericalMappingTests(unittest.TestCase):
    def claim(self):
        return {"claim_id": "toy-score", "unit": "fraction", "tolerance": 0,
                "required_locations": ["abstract", "body", "table", "caption", "ledger"],
                "occurrences": [{"location": location, "value": 0.5, "unit": "fraction"}
                                for location in ("abstract", "body", "table", "caption", "ledger")]}

    def test_all_explicit_locations_agree_across_supported_input_shapes(self):
        claim = self.claim()
        mapped = copy.deepcopy(claim)
        del mapped["claim_id"]
        for shape in ([claim], {"claims": [claim]}, claim, {"toy-score": mapped}):
            with self.subTest(shape=type(shape)):
                self.assertTrue(numbers(shape)["passed"])
        self.assertEqual(numbers([])["status"], "not_applicable")

    def test_disagreement_does_not_select_a_winning_value(self):
        claim = self.claim()
        claim["occurrences"][3]["value"] = 0.7
        result = numbers([claim])
        self.assertFalse(result["passed"])
        self.assertEqual(result["claims"][0]["observed"], claim["occurrences"])
        self.assertFalse(result["claims"][0]["evidence"]["winner_selected"])

    def test_missing_duplicate_units_and_boolean_values_fail(self):
        for defect in ("missing", "duplicate", "unit", "boolean"):
            claim = self.claim()
            if defect == "missing":
                claim["occurrences"].pop()
            elif defect == "duplicate":
                claim["occurrences"].append(claim["occurrences"][0])
            elif defect == "unit":
                claim["occurrences"][0].update(value=50, unit="percent")
            else:
                claim["occurrences"][0]["value"] = True
            with self.subTest(defect=defect):
                self.assertFalse(numbers([claim])["passed"])

    def test_tolerance_covers_the_entire_span_not_only_one_anchor(self):
        claim = self.claim()
        claim["tolerance"] = 0.11
        claim["occurrences"][0]["value"] = 0.4
        claim["occurrences"][1]["value"] = 0.6
        self.assertFalse(numbers([claim])["passed"])
        claim["tolerance"] = 0.21
        self.assertTrue(numbers([claim])["passed"])

    def test_nonfinite_and_ambiguous_numeric_definitions_are_rejected(self):
        claim = self.claim()
        claim["occurrences"][0]["value"] = float("nan")
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            numbers([claim])
        claim = self.claim()
        with self.assertRaisesRegex(ValueError, "duplicate numeric"):
            numbers([claim, claim])
        claim["required_locations"] = ["body"]
        with self.assertRaisesRegex(ValueError, "at least two"):
            numbers([claim])


if __name__ == "__main__":
    unittest.main()
