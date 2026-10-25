"""Interrupted metadata capture, logging isolation and library-scoped receipts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from researchvault import intake, resolution

try:
    from tests import test_identifier_intake as fixtures
except ModuleNotFoundError:
    import test_identifier_intake as fixtures


@unittest.skipUnless(importlib.util.find_spec("pypdf"), "Optional pypdf required")
class IntakeRecoveryTests(unittest.TestCase):
    # Reuse the synthetic setup without inheriting and rerunning its entire suite.
    setUp = fixtures.IdentifierIntakeTests.setUp
    run_intake = fixtures.IdentifierIntakeTests.run_intake
    note = fixtures.IdentifierIntakeTests.note

    def test_resume_after_metadata_capture_uses_frozen_envelope_without_resolving_again(self):
        def stop_after_capture(stage):
            if stage == "after_metadata_capture":
                raise RuntimeError("Synthetic crash after metadata capture")

        with self.assertRaisesRegex(RuntimeError, "after metadata capture"):
            self.run_intake(crash=stop_after_capture)
        candidates = list(self.settings.runtime.glob("intake/workflows/*/candidate.json"))
        self.assertEqual(len(candidates), 1)
        frozen_path = candidates[0]
        frozen_bytes = frozen_path.read_bytes()
        envelope = json.loads(frozen_bytes)
        digest = hashlib.sha256(intake._bytes(envelope["candidate"])).hexdigest()
        self.assertEqual(envelope["sha256"], digest)
        self.assertFalse(frozen_path.with_name("state.json").exists())
        self.assertFalse(any(call[0] == "POST" for call in self.local.calls))

        no_resolution = Mock(side_effect=AssertionError("Resume must use its existing captured metadata"))
        blocked = self.run_intake(resolver=no_resolution)
        self.assertEqual(blocked["items"][0]["status"], "RESUME_REQUIRED", blocked)
        resumed = self.run_intake(resume=True, resolver=no_resolution)
        self.assertEqual(resumed["status"], "COMPLETE", resumed)
        no_resolution.assert_not_called()
        self.assertEqual(frozen_path.read_bytes(), frozen_bytes)
        state = json.loads(frozen_path.with_name("state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["candidate_sha256"], digest)
        self.assertEqual(resumed["counts"]["parent_created"], 1)
        self.assertEqual(resumed["counts"]["attachment_created"], 1)
        self.assertEqual(sum("api.crossref.org" in url for url in self.public.calls), 1)

    def test_first_item_event_append_error_is_reported_and_second_item_continues(self):
        request_id = resolution.parse(fixtures.DOI)["canonical_id"]
        first_token = hashlib.sha256(("users/0\n" + request_id).encode()).hexdigest()
        original_open = Path.open
        denied_appends = []

        def deny_first_item_log(path, mode="r", *args, **kwargs):
            if path.name == "events.jsonl" and path.parent.name == first_token and mode == "ab":
                denied_appends.append(path)
                raise PermissionError("Synthetic first-item event append failure")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", new=deny_first_item_log):
            result = self.run_intake([fixtures.DOI, "arxiv:" + fixtures.ARXIV_BASE + "v2"])
        self.assertEqual(result["status"], "PARTIAL", result)
        self.assertEqual(len(result["items"]), 2, result)
        self.assertEqual(result["blocked"], 1, result)
        self.assertGreaterEqual(len(denied_appends), 2)
        self.assertEqual(result["items"][0]["status"], "ITEM_FAILED")
        self.assertTrue(result["items"][0]["logging_failure"])
        self.assertEqual(result["items"][1]["status"], "ARCHIVED_ANALYSIS_PENDING")
        self.assertTrue(result["items"][1]["zotero_read_back_verified"])
        self.assertEqual(result["counts"]["parent_created"], 1)
        self.assertEqual(result["counts"]["attachment_created"], 1)
        self.assertEqual(len(list(self.settings.folder("papers").rglob("*.md"))), 1)

    def test_same_canonical_identity_uncertain_receipt_in_another_library_is_ignored(self):
        candidate = resolution.resolve(fixtures.DOI, transport=self.public)
        request_id = resolution.parse(fixtures.DOI)["canonical_id"]
        other_namespace = "groups/42"
        token = hashlib.sha256((other_namespace + "\n" + request_id).encode()).hexdigest()
        directory = self.settings.runtime / "intake" / "workflows" / token
        directory.mkdir(parents=True)
        digest = hashlib.sha256(intake._bytes(candidate)).hexdigest()
        (directory / "candidate.json").write_bytes(intake._bytes({"candidate": candidate, "sha256": digest}))
        (directory / "state.json").write_bytes(intake._bytes({
            "schema_version": 1, "request_id": request_id, "canonical_id": candidate["canonical_id"],
            "candidate_sha256": digest, "library": other_namespace, "server_id": self.local.server,
            "status": "MANUAL_RECONCILIATION_REQUIRED"}))
        # A matching server ID ensures the regression exercises library isolation,
        # rather than being stopped first by a different-server check.
        receipt = directory / "parent.jsonl"
        receipt.write_bytes(intake._bytes({"status": "INTENT", "operation": "create_parent",
                                          "library": other_namespace, "server_id": self.local.server}) + b"\n")
        original_files = {path: path.read_bytes() for path in directory.iterdir()}

        result = self.run_intake()
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertEqual(result["library"], "users/0")
        self.assertEqual(result["counts"]["parent_created"], 1)
        self.assertEqual(result["counts"]["attachment_created"], 1)
        self.assertEqual({path: path.read_bytes() for path in original_files}, original_files)
        self.assertEqual(len(receipt.read_text(encoding="utf-8").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
