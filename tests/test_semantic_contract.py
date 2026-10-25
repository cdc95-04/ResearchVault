"""Recorded-review integrity boundaries; no PDF, QA storage or semantic oracle."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import semantic_contract as contract


class SemanticContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="semantic-contract-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        origin = Path(__file__).resolve().parent.parent
        freeze = contract.read_json(origin / "validation/golden/b2/freeze.json")
        names = list(freeze["files"]) + ["validation/golden/b2/" + name for name in (
            "freeze.json", "semantic_cases.json", "semantic_rubric.json",
            "semantic_captures.json", "semantic_results.json", "sac_revision.json",
            "sac_revision_review.json")]
        for name in names:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin / name, target)
        self.b2 = self.root / "validation/golden/b2"
        self.capture_path = self.b2 / "semantic_captures.json"
        self.result_path = self.b2 / "semantic_results.json"
        self.capture = contract.read_json(self.capture_path)
        self.result = contract.read_json(self.result_path)

    def save(self, path, document):
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")

    def save_reviews(self):
        self.save(self.capture_path, self.capture)
        self.result["captures_digest"] = contract.text_digest(self.capture_path)
        self.result["results"] = [dict(row, case_id=self.result["blind_map"][row["case_id"]],
            blind_case_id=row["case_id"]) for row in self.capture["reviews"]]
        self.save(self.result_path, self.result)

    def assert_invalid(self, code, **kwargs):
        report = contract.validate_contract(self.root, **kwargs)
        self.assertFalse(report["valid"], report)
        self.assertEqual(report["errors"][0]["code"], code)
        self.assertIs(report["semantic_judgment_performed"], False)

    def test_default_public_contract_needs_no_qa_or_pdf_and_is_read_only(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        report = contract.validate_contract(self.root)
        self.assertTrue(report["valid"], report)
        self.assertFalse(report["checks"]["freeze"]["pdf_hashes_checked"])
        self.assertEqual(report["checks"]["freeze"]["counts"], {
            "expected_claims": 9, "numerical_expectations": 26,
            "retrieval_queries": 6, "deliberate_invalid_cases": 33})
        self.assertFalse((self.root / ".qa").exists())
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_lf_and_crlf_are_equivalent_but_real_frozen_drift_is_rejected(self):
        for path in self.root.rglob("*"):
            if path.is_file():
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertTrue(contract.validate_contract(self.root)["valid"])
        changed = self.root / "validation/golden/captures/sac2018.json"
        changed.write_bytes(changed.read_bytes() + b" ")
        with self.assertRaises(contract.ContractError) as caught:
            contract.verify_freeze(self.root)
        self.assertEqual(caught.exception.code, "STALE_FROZEN_FILE")
        self.assert_invalid("STALE_FROZEN_FILE")

    def test_agent_pass_is_not_a_new_semantic_decision_by_the_contract(self):
        # The fixed candidate includes a known bad observation. This contract
        # deliberately accepts a well-formed recorded PASS and does not act as
        # a scientific oracle or infer a verdict from an injected-error label.
        row = self.capture["reviews"][0]
        for dimension in row["dimensions"].values():
            dimension["status"] = "PASS"
            dimension["reason"] = "Recorded agent judgment requiring independent source review."
        row["verdict"] = "PASS"
        row["reason"] = "Recorded agent PASS; its correctness is outside this contract."
        self.save_reviews()
        report = contract.validate_contract(self.root)
        self.assertTrue(report["valid"], report)
        self.assertFalse(report["semantic_judgment_performed"])

    def test_missing_dimension_remains_an_error_even_if_mapping_is_consistent(self):
        del self.capture["reviews"][0]["dimensions"]["LIMITATION"]
        self.save_reviews()
        self.assert_invalid("DIMENSION_INVENTORY")

    def test_nonapplicable_and_uncertain_states_cannot_be_promoted(self):
        row = self.capture["reviews"][0]
        row["dimensions"]["MECHANISM"]["status"] = "UNCERTAIN"
        self.save_reviews()
        self.assert_invalid("NONAPPLICABLE_STATE")
        row["dimensions"]["MECHANISM"]["applicable"] = True
        for dimension in row["dimensions"].values():
            if dimension["status"] == "FAIL":
                dimension["status"] = "PASS"
        row["verdict"] = "PASS"
        self.save_reviews()
        self.assert_invalid("VERDICT_AGGREGATION")

    def test_mapping_cannot_rewrite_a_review_reason_or_candidate(self):
        self.result["results"][0]["reason"] = "An edited summary replacing the captured decision."
        self.save(self.result_path, self.result)
        self.assert_invalid("CAPTURE_CHANGED")
        self.capture["reviews"][0]["claim"] += " Additional unreviewed material."
        self.save_reviews()
        self.assert_invalid("CANDIDATE_CHANGED")

    def test_anchor_bounds_and_independence_disclosures_are_required(self):
        self.capture["reviews"][0]["evidence_anchor"]["pdf_page"] = 1000000
        self.save_reviews()
        self.assert_invalid("PAGE_BOUNDS")
        self.capture["reviews"][0]["evidence_anchor"]["pdf_page"] = 7
        self.capture["reviewer"]["prior_verdict_seen"] = True
        self.result["reviewer"] = copy.deepcopy(self.capture["reviewer"])
        self.save_reviews()
        self.assert_invalid("INDEPENDENCE_DISCLOSURE")

    def test_agent_cannot_self_promote_human_review_or_embed_inline_approval(self):
        self.result["human_review_status"] = "reviewed"
        self.result["human_decisions"] = {"review_kind": "human_review", "approved": True}
        self.save(self.result_path, self.result)
        self.assert_invalid("HUMAN_STATUS")

    def test_explicit_human_decisions_bind_all_cases_and_actual_capture(self):
        self.result["human_review_status"] = "reviewed"
        self.save(self.result_path, self.result)
        decisions = {"review_kind": "human_review", "reviewer": {"identity": "Named test reviewer"},
            "captures_digest": contract.text_digest(self.capture_path), "decisions": [
                {"case_id": key, "decision": "REVISE_GOLD", "reviewed_on": "2026-10-04",
                 "source_evidence": "Explicit human decision fixture; not a real approval."}
                for key in self.result["blind_map"].values()]}
        path = self.root / "explicit-human-decisions.json"
        self.save(path, decisions)
        self.assertTrue(contract.validate_contract(self.root, human_decisions_path=path)["valid"])
        decisions["decisions"].pop()
        self.save(path, decisions)
        self.assert_invalid("HUMAN_DECISION", human_decisions_path=path)

    def test_explicit_wrong_pdf_is_rejected_before_any_parsing(self):
        papers = self.root / "explicit-papers"
        papers.mkdir()
        (papers / "sac2018.pdf").write_bytes(b"Not the frozen public source PDF")
        with self.assertRaises(contract.ContractError) as caught:
            contract.verify_freeze(self.root, papers_dir=papers)
        self.assertEqual(caught.exception.code, "PDF_DIGEST")

    def test_coordinated_case_and_capture_edit_cannot_replace_a_frozen_injection(self):
        path = self.b2 / "semantic_cases.json"
        cases = contract.read_json(path)
        cases["cases"][0]["candidate"]["observation"] = "A different unreviewed assertion."
        self.save(path, cases)
        self.result["cases_digest"] = contract.text_digest(path)
        self.capture["reviews"][0]["claim"] = self.capture["reviews"][0]["claim"].replace(
            "The reported success rate is 98765 percent.", "A different unreviewed assertion.")
        self.save_reviews()
        self.assert_invalid("CASE_BINDING")

    def test_case_owner_and_responsibility_flags_are_schema_declarations(self):
        path = self.b2 / "semantic_cases.json"
        original = contract.read_json(path)
        for field, value in (("recommended_owner", "AUTO_PROSE_JUDGE"),
                             ("deterministically_checkable", "false")):
            changed = copy.deepcopy(original)
            changed["cases"][0][field] = value
            self.save(path, changed)
            with self.subTest(field=field):
                self.assert_invalid("CASE_FIELDS")

    def test_current_sac_revision_cannot_reuse_a_review_of_an_older_statement(self):
        report = contract.verify_sac_revision(self.root)
        self.assertTrue(report["valid"])
        self.assertFalse(report["semantic_judgment_performed"])
        path = self.b2 / "sac_revision.json"
        revision = contract.read_json(path)
        revision["revised_statement"] += " An additional claim has not been reviewed."
        self.save(path, revision)
        with self.assertRaises(contract.ContractError) as caught:
            contract.verify_sac_revision(self.root)
        self.assertEqual(caught.exception.code, "SAC_REVIEW_STALE")

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(self):
        path = self.root / "bad.json"
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}'):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    contract.read_json(path)


if __name__ == "__main__":
    unittest.main()
