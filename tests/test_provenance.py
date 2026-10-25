"""Synthetic receipt tests; no real paper or personal Vault data."""
import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from researchvault.config import load_settings
from researchvault.documents import scan, write_new
from researchvault import provenance


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "synthetic-vault"
        self.settings = load_settings(vault=self.root, synthetic=True)
        self.root.mkdir()

    def test_canonical_dates_mapping_order_and_finite_domain(self):
        self.assertEqual(provenance.digest({"b": date(2026, 1, 2), "a": 1}),
                         provenance.digest({"a": 1, "b": "2026-01-02"}))
        utc = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self.assertEqual(provenance.canonical(utc), provenance.canonical(utc.astimezone(timezone(timedelta(hours=8)))))
        cycle = []
        cycle.append(cycle)
        for value in [float("nan"), float("inf"), {1: "not JSON"}, {"a"}, cycle]:
            with self.subTest(value=type(value).__name__), self.assertRaises(ValueError):
                provenance.canonical(value)

    def create(self, content, **kwargs):
        return provenance.create_receipt(self.settings, kind="claim", object_id="card-test",
                                         source="card.md", content=content, **kwargs)

    def test_preview_and_bad_serialization_do_not_create_metadata(self):
        preview = self.create({"proposition": "synthetic"})
        self.assertFalse(preview["applied"])
        self.assertFalse(self.settings.folder("metadata").exists())
        with self.assertRaises(ValueError):
            self.create({"bad": float("nan")}, apply=True)
        self.assertFalse(self.settings.folder("metadata").exists())

    def test_removed_page_reference_cannot_reset_history(self):
        first = self.create({"proposition": "before"}, apply=True)
        with self.assertRaisesRegex(ValueError, "predecessor"):
            self.create({"proposition": "after"}, apply=True)
        second = self.create({"proposition": "after"}, previous=first["digest"], reason="narrow scope", apply=True)
        self.assertEqual(len(provenance.history(self.settings, "claim", "card-test")), 2)
        self.assertTrue(self.settings.resolve(first["receipt"]).is_file())
        with self.assertRaisesRegex(ValueError, "historical"):
            self.create({"proposition": "before"}, apply=True)
        self.assertEqual(second["envelope"]["previous"], first["digest"])

    def test_tampered_and_branched_history_fail_closed(self):
        first = self.create({"v": 1}, apply=True)
        second = self.create({"v": 2}, previous=first["digest"], reason="change", apply=True)
        target = self.settings.resolve(second["receipt"])
        data = json.loads(target.read_text())
        data["snapshot"]["v"] = 3
        target.write_text(json.dumps(data))
        diagnostics = provenance.check(self.settings, [])
        self.assertTrue(diagnostics)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.create({"v": 4}, previous=second["digest"], reason="change", apply=True)

    def test_post_result_lineage_cannot_become_pre_result(self):
        first = self.create({"v": 1}, timing="post-result", apply=True)
        with self.assertRaisesRegex(ValueError, "post-result lineage"):
            self.create({"v": 2}, previous=first["digest"], reason="revise", timing="pre-result")

    def test_snapshot_detects_source_artifact_change_without_changing_page(self):
        page = self.root / "concept.md"
        write_new(page, {"type": "concept", "schema_version": 2}, "A synthetic concept.\n")
        (self.root / "source.txt").write_text("original source")
        before = page.read_bytes()
        result = provenance.snapshot(self.settings, "concept.md", sources=["source.txt"], apply=True)
        self.assertEqual(before, page.read_bytes())
        self.assertEqual(provenance.check(self.settings, scan(self.settings)), [])
        (self.root / "source.txt").write_text("changed source")
        self.assertTrue(any(item["code"] == "provenance.receipt" for item in provenance.check(self.settings, scan(self.settings))))
        self.assertIn("provenance_digest", result["metadata"])

    def test_ordinary_concept_requires_no_sidecar(self):
        write_new(self.root / "concept.md", {"type": "concept", "schema_version": 2}, "Synthetic concept.\n")
        self.assertEqual(provenance.check(self.settings, scan(self.settings)), [])

    def test_malformed_receipt_shape_is_controlled_diagnostic(self):
        result = self.create({"v": 1}, apply=True)
        data = result["envelope"]
        data["snapshot"] = []
        self.settings.resolve(result["receipt"]).write_text(json.dumps(data))
        issues = provenance.check(self.settings, [])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["level"], "error")


if __name__ == "__main__":
    unittest.main()
