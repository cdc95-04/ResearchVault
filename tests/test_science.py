"""Independent synthetic behavior cases for scientific record accounting."""
import copy
import tempfile
import unittest
from pathlib import Path

import yaml

from researchvault import process
from researchvault.config import load_settings
from researchvault.documents import scan


class ScienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "synthetic-vault"
        self.root.mkdir()
        self.settings = load_settings(vault=self.root, synthetic=True)
        self.card = {"schema_version": 2, "type": "research-card", "card_id": "card-01", "claim_id": "claim-01",
                     "proposition": "A synthetic controller reduces error in the declared simulator",
                     "scope": {"setting": "simulation"}, "comparisons": ["fixed controller"],
                     "mechanism": "declared feedback law", "falsifiers": ["no improvement"],
                     "evidence_obligations": ["all attempt logs"]}
        self.put("card.md", self.card)
        self.claim = process.freeze(self.settings, "card.md", "claim", apply=True)
        self.card.update(self.claim["metadata"])
        self.put("card.md", self.card)
        self.contract = {"schema_version": 2, "type": "experiment-contract", "experiment_id": "exp-01",
                         "card_id": "card-01", "claim_id": "claim-01", "claim_digest": self.claim["digest"],
                         "conditions": ["control", "candidate"], "baselines": ["control"], "metrics": ["error"],
                         "denominator": {"unit": "attempt", "include_statuses": ["completed", "failed", "aborted"]},
                         "exclusions": [{"reason": "corrupt sensor before motion"}],
                         "abort_policy": {"allowed_reasons": ["safety stop"], "include_in_denominator": True},
                         "seeds": [1, 2], "analysis_plan": "Report all attempts and paired errors."}
        self.put("contract.md", self.contract)
        self.design = process.freeze(self.settings, "contract.md", "design", apply=True)
        self.contract.update(self.design["metadata"])
        self.put("contract.md", self.contract)
        (self.root / "raw.txt").write_text("synthetic raw measurement: 0.2\n")
        (self.root / "analysis.txt").write_text("synthetic analysis result\n")

    def put(self, path, data):
        (self.root / path).write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nSynthetic fixture.\n", encoding="utf-8")

    def trial(self, identifier, status="completed", **fields):
        row = {"schema_version": 2, "type": "experiment-trial", "trial_id": identifier,
               "experiment_id": "exp-01", "design_digest": self.design["digest"],
               "condition": "candidate", "seed": 1, "robot": "synthetic-arm", "environment": "sim-A",
               "git_commit": "a" * 40, "config": {"gain": 0.5}, "raw_artifacts": ["raw.txt"],
               "status": status, "included_in_denominator": status != "excluded"}
        row.update(fields)
        self.put(identifier + ".md", row)
        return row

    def result(self, ids, **fields):
        row = {"schema_version": 2, "type": "result-bundle", "result_id": "result-01",
               "experiment_id": "exp-01", "claim_id": "claim-01", "claim_digest": self.claim["digest"],
               "design_digest": self.design["digest"], "trial_ids": ids, "verdict": "INCONCLUSIVE",
               "status": "completed", "analysis_artifacts": ["analysis.txt"], "missingness": [],
               "evidence_ceiling": {key: [] for key in process.CEILINGS}}
        row["evidence_ceiling"]["setting"] = ["simulation"]
        row.update(fields)
        self.put("result.md", row)
        return row

    def diagnostics(self):
        return process.check(self.settings, scan(self.settings))

    def test_freeze_proposes_metadata_without_editing_human_page(self):
        before = (self.root / "card.md").read_bytes()
        frozen = process.freeze(self.settings, "card.md", "claim", apply=True)
        self.assertEqual(before, (self.root / "card.md").read_bytes())
        self.assertTrue(frozen["existing"])
        self.assertEqual(self.diagnostics(), [])

    def test_scientific_drift_and_removed_reference_both_detected(self):
        self.card["scope"] = {"setting": "all physical robots"}
        self.put("card.md", self.card)
        self.assertTrue(self.diagnostics())
        for key in self.claim["metadata"]:
            del self.card[key]
        self.put("card.md", self.card)
        self.assertTrue(any(item["code"] == "science.lock-reference" for item in self.diagnostics()))
        with self.assertRaisesRegex(ValueError, "predecessor"):
            process.freeze(self.settings, "card.md", "claim", apply=True)

    def test_failed_aborted_excluded_and_retry_all_remain_accounted(self):
        self.trial("failed", "failed")
        self.trial("aborted", "aborted", abort_reason="safety stop")
        self.trial("excluded", "excluded", exclusion_reason="corrupt sensor before motion")
        self.trial("retry", retry_of="failed")
        self.result(["failed", "aborted", "excluded", "retry"])
        self.assertEqual(self.diagnostics(), [])
        self.result(["retry"])
        self.assertTrue(any("every attempt" in item["detail"] for item in self.diagnostics()))
        self.result(["failed", "aborted", "excluded", "retry"])
        (self.root / "failed.md").unlink()
        self.assertTrue(any("prior trial" in item["detail"] or "every attempt" in item["detail"] for item in self.diagnostics()))

    def test_denominator_and_unplanned_abort_cannot_be_waived(self):
        self.trial("aborted", "aborted", abort_reason="safety stop", included_in_denominator=False)
        self.assertTrue(any("denominator" in item["detail"] for item in self.diagnostics()))
        self.trial("aborted", "aborted", abort_reason="bad outcome")
        self.assertTrue(any("abort reason" in item["detail"] for item in self.diagnostics()))

    def test_missing_artifacts_are_explicit_and_block_supported_verdict(self):
        self.trial("done")
        self.trial("failed", "failed", raw_artifacts=[], missingness_reason="logger crashed")
        self.result(["done", "failed"], missingness=[{"trial_id": "failed", "reason": "logger crashed"}])
        self.assertEqual(self.diagnostics(), [])
        self.result(["done", "failed"], verdict="SUPPORTED", missingness=[{"trial_id": "failed", "reason": "logger crashed"}])
        self.assertTrue(any("definitive verdict" in item["detail"] for item in self.diagnostics()))

    def test_post_result_revision_is_exploratory_and_old_result_keeps_design(self):
        self.trial("done")
        self.result(["done"])
        original_digest = self.design["digest"]
        self.contract["analysis_plan"] = "An additional exploratory sensitivity analysis."
        self.put("contract.md", self.contract)
        with self.assertRaisesRegex(ValueError, "post-result"):
            process.freeze(self.settings, "contract.md", "design", previous=original_digest, reason="inspect sensitivity", apply=True)
        update = process.freeze(self.settings, "contract.md", "design", previous=original_digest,
                                reason="inspect sensitivity", timing="post-result", apply=True)
        self.contract.update(update["metadata"])
        self.put("contract.md", self.contract)
        self.assertEqual(update["metadata"]["design_lock_status"], "exploratory")
        self.assertEqual(self.diagnostics(), [])
        self.assertTrue(self.settings.resolve(self.design["receipt"]).exists())

    def test_ledger_cannot_promote_inconclusive_or_expand_robot_scope(self):
        self.trial("done")
        result = self.result(["done"])
        ledger = {"schema_version": 2, "type": "claim-ledger", "claim_id": "claim-01", "verdict": "SUPPORTED",
                  "result_ids": ["result-01"], "literature": [], "evidence_ceiling": copy.deepcopy(result["evidence_ceiling"])}
        self.put("ledger.md", ledger)
        self.assertTrue(any("relabel" in item["detail"] for item in self.diagnostics()))
        ledger["verdict"] = "INCONCLUSIVE"
        ledger["evidence_ceiling"]["robot"] = ["any robot"]
        self.put("ledger.md", ledger)
        self.assertTrue(any("ceiling" in item["detail"] for item in self.diagnostics()))

    def test_claim_identity_cannot_reset_post_result_history(self):
        self.trial("done")
        self.result(["done"])
        self.card["claim_id"] = "renamed-claim"
        self.card["proposition"] = "A replacement claim proposed after observing results"
        self.put("card.md", self.card)
        with self.assertRaisesRegex(ValueError, "claim_id must remain stable"):
            process.freeze(self.settings, "card.md", "claim", previous=self.claim["digest"],
                           reason="rename after results", apply=True)
        self.assertTrue(any("claim_id must remain stable" in item["detail"] for item in self.diagnostics()))

        # A well-hashed receipt created through the generic API cannot waive the
        # specialized scientific identity rule during later validation.
        from researchvault.provenance import create_receipt
        receipt = create_receipt(self.settings, kind="claim", object_id="card-01", source="card.md",
                                 content=process.lock_content(self.card, "claim"), previous=self.claim["digest"],
                                 reason="rename after results", timing="pre-result", apply=True)
        self.card.update(claim_digest=receipt["digest"], claim_receipt=receipt["receipt"])
        self.put("card.md", self.card)
        self.assertTrue(any("claim_id must remain stable" in item["detail"] for item in self.diagnostics()))

    def test_definitive_ledger_cannot_use_draft_result_without_analysis(self):
        self.trial("done")
        result = self.result(["done"], verdict="SUPPORTED", status="draft", analysis_artifacts=[])
        self.assertEqual(self.diagnostics(), [])
        self.put("ledger.md", {"schema_version": 2, "type": "claim-ledger", "claim_id": "claim-01",
                               "verdict": "SUPPORTED", "result_ids": ["result-01"], "literature": [],
                               "evidence_ceiling": copy.deepcopy(result["evidence_ceiling"])})
        self.assertTrue(any("completed result evidence" in item["detail"] for item in self.diagnostics()))
        self.result(["done"], verdict="SUPPORTED")
        self.assertEqual(self.diagnostics(), [])

    def test_malformed_optional_mapping_is_diagnostic_not_exception(self):
        self.trial("done", config=["not", "a", "mapping"])
        issues = self.diagnostics()
        self.assertTrue(issues)
        self.assertEqual(set(issues[0]), {"code", "path", "detail", "level"})


if __name__ == "__main__":
    unittest.main()
