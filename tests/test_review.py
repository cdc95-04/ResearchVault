"""Synthetic corpus freezes and evidence-based external review gates."""
import copy
import tempfile
import unittest
from pathlib import Path

import yaml

from researchvault import review
from researchvault.config import load_settings
from researchvault.documents import scan


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "synthetic-vault"
        self.root.mkdir()
        self.settings = load_settings(vault=self.root, synthetic=True)
        self.protocol = {"schema_version": 2, "type": "review-protocol", "review_id": "review-01", "version": 1,
                         "scope": "Synthetic feedback mechanisms in simulation", "inclusion_criteria": ["explicit mechanism"],
                         "exclusion_criteria": ["no experimental comparison"], "sources": ["synthetic-index"],
                         "seed_papers": [], "citation_policy": {"max_rounds": 1, "directions": ["backward", "forward"]},
                         "query_families": [{"family_id": "mechanism", "purpose": "mechanisms", "queries": ["feedback mechanism"]},
                                            {"family_id": "task", "purpose": "tasks", "queries": ["controller task"]}],
                         "corpus_path": "corpus.yaml"}
        self.paper_id = "doi:10.9999/synthetic-test"
        self.corpus = {"schema_version": 2, "review_id": "review-01", "protocol_version": 1,
                       "searches": [{"family_id": family["family_id"], "query": family["queries"][0],
                                     "source": "synthetic-index", "executed_at": "2026-01-02", "returned_ids": [self.paper_id]}
                                    for family in self.protocol["query_families"]],
                       "papers": [{"paper_id": self.paper_id, "decision": "include", "reason": "synthetic comparator"}],
                       "deduplication": {"performed": True, "method": "canonical DOI", "duplicates": []},
                       "citation_rounds": [], "challenges": [{"type": kind, "query": "synthetic " + kind,
                                                                "source": "synthetic-index", "executed_at": "2026-01-02", "found_ids": []}
                                                               for kind in sorted(review.CHALLENGES)],
                       "coverage": {"dimensions": {"setting": ["simulation"]}, "limits": ["single synthetic source"],
                                    "unsearched": ["Citation sources are unavailable in this synthetic fixture"]},
                       "evidence_matrix": []}
        self.save()

    def put(self, path, data, body="Synthetic fixture.\n"):
        (self.root / path).write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n" + body, encoding="utf-8")

    def save(self):
        self.put("protocol.md", self.protocol)
        (self.root / "corpus.yaml").write_text(yaml.safe_dump(self.corpus, sort_keys=False), encoding="utf-8")

    def lock(self, **kwargs):
        self.save()
        result = review.freeze(self.settings, "protocol.md", apply=True, **kwargs)
        self.protocol.update(result["metadata"])
        self.save()
        return result

    def gap(self, **kwargs):
        data = {"schema_version": 2, "type": "research-gap", "gap_id": "gap-01", "review_id": "review-01",
                "corpus_digest": self.protocol["corpus_digest"], "review_status": "externally_checked", "confidence": "medium"}
        data.update(kwargs)
        self.put("gap.md", data)

    def check(self):
        return review.check(self.settings, scan(self.settings))

    def test_corpus_freeze_is_create_only_and_has_no_paper_quota(self):
        before = (self.root / "protocol.md").read_bytes()
        result = review.freeze(self.settings, "protocol.md", apply=True)
        self.assertEqual(before, (self.root / "protocol.md").read_bytes())
        self.protocol.update(result["metadata"])
        self.save()
        self.gap()
        self.assertEqual(self.check(), [])

    def test_new_paper_requires_versioned_revision_and_old_corpus_remains(self):
        first = self.lock()
        added = "doi:10.9999/another-test"
        self.corpus["papers"].append({"paper_id": added, "decision": "exclude", "reason": "outside scope"})
        self.corpus["searches"][0]["returned_ids"].append(added)
        self.save()
        self.assertTrue(self.check())
        with self.assertRaisesRegex(ValueError, "new protocol version"):
            review.freeze(self.settings, "protocol.md", previous=first["digest"], reason="new candidate", apply=True)
        self.protocol["version"] = self.corpus["protocol_version"] = 2
        self.save()
        second = self.lock(previous=first["digest"], reason="new candidate")
        self.assertNotEqual(first["digest"], second["digest"])
        self.assertTrue(self.settings.resolve(first["receipt"]).exists())
        self.assertEqual(self.check(), [])

    def test_missing_challenge_and_fake_family_execution_block_external_gap(self):
        self.corpus["challenges"].pop()
        self.lock()
        self.gap()
        self.assertTrue(any("five challenge" in item["detail"] for item in self.check()))
        self.corpus["searches"] = self.corpus["searches"][:1]
        with self.assertRaisesRegex(ValueError, "distinct query families"):
            review._external_gate(self.corpus)

    def test_screening_dedup_and_candidate_accounting_are_not_labels_only(self):
        for change in (lambda c: c["papers"][0].update(reason=""),
                       lambda c: c["searches"][0]["returned_ids"].append("doi:10.9999/unscreened"),
                       lambda c: c.update(deduplication=[])):
            candidate = copy.deepcopy(self.corpus)
            change(candidate)
            with self.assertRaises(ValueError):
                review.corpus_content(self.protocol, candidate)
        self.corpus["deduplication"]["performed"] = False
        self.lock()
        self.gap()
        self.assertTrue(any("deduplication" in item["detail"] for item in self.check()))

    def test_citation_round_bound_is_enforced(self):
        self.corpus["citation_rounds"] = [{"direction": "backward", "round": 2,
                                            "seed_ids": [self.paper_id], "found_ids": [], "executed_at": "2026-01-02"}]
        self.save()
        with self.assertRaisesRegex(ValueError, "bound"):
            review.freeze(self.settings, "protocol.md", apply=True)

    def add_critical_evidence(self, quote="Synthetic feedback reduced error in simulation."):
        identity = {"zotero_key": "TESTP001", "pdf_key": "TESTA001", "library_id": None,
                    "doi": "10.9999/synthetic-test"}
        self.put("note.md", {"schema_version": 2, "type": "literature-note", "fulltext_path": "fulltext.md", **identity})
        self.put("fulltext.md", {"schema_version": 2, "type": "literature-fulltext", **identity},
                 "Synthetic feedback reduced error in simulation.\n")
        self.corpus["evidence_matrix"] = [{"paper_id": self.paper_id, "note_path": "note.md", "position": "supporting",
                                            "finding": "Limited synthetic evidence", "critical": True,
                                            "evidence_status": "fulltext_verified",
                                            "verification": [{"fulltext_path": "fulltext.md", "zotero_key": "TESTP001",
                                                              "pdf_key": "TESTA001", "quote": quote}]}]
        self.save()

    def test_high_gap_requires_actual_critical_source_evidence(self):
        self.add_critical_evidence()
        self.lock()
        self.gap(confidence="high", evidence_ids=[self.paper_id])
        self.assertEqual(self.check(), [])
        (self.root / "fulltext.md").write_text("---\ntype: literature-fulltext\nschema_version: 2\nzotero_key: TESTP001\npdf_key: TESTA001\nlibrary_id: null\n---\nDifferent source text.")
        self.assertTrue(any("verification failed" in item["detail"] for item in self.check()))

    def test_high_gap_rejects_unrelated_note_and_missing_critical_rows(self):
        self.lock()
        self.gap(confidence="high", evidence_ids=[self.paper_id])
        self.assertTrue(any("critical corpus evidence" in item["detail"] for item in self.check()))

    def test_historical_gap_keeps_its_original_frozen_evidence(self):
        self.add_critical_evidence()
        first = self.lock()
        self.gap(confidence="high", evidence_ids=[self.paper_id])
        original_gap = (self.root / "gap.md").read_bytes()
        self.protocol["version"] = self.corpus["protocol_version"] = 2
        self.corpus["evidence_matrix"] = []
        self.lock(previous=first["digest"], reason="Begin a separately scoped evidence matrix")
        self.assertEqual(self.check(), [])
        self.assertEqual((self.root / "gap.md").read_bytes(), original_gap)
        (self.root / "fulltext.md").write_text("---\ntype: literature-fulltext\nschema_version: 2\n"
                                               "zotero_key: TESTP001\npdf_key: TESTA001\nlibrary_id: null\n"
                                               "---\nChanged source text.", encoding="utf-8")
        self.assertTrue(any("verification failed" in item["detail"] for item in self.check()))

    def test_corpus_rejects_fake_or_noncanonical_publication_identities(self):
        invalid = ["doi:bananas", "doi:10.9999/MixedCase", "arxiv:anything", "zotero:other:local:TESTP001",
                   "zotero:user:local:short", "zotero:group:0:TESTP001", "zotero:group:01:TESTP001"]
        for identifier in invalid:
            with self.subTest(identifier=identifier):
                corpus = copy.deepcopy(self.corpus)
                corpus["papers"][0]["paper_id"] = identifier
                for search in corpus["searches"]:
                    search["returned_ids"] = [identifier]
                with self.assertRaises(ValueError):
                    review.corpus_content(self.protocol, corpus)
        for identifier in ["doi:10.9999/valid", "arxiv:2401.01234v2", "zotero:user:local:TESTP001", "zotero:group:42:TESTP001"]:
            with self.subTest(identifier=identifier):
                corpus = copy.deepcopy(self.corpus)
                corpus["papers"][0]["paper_id"] = identifier
                for search in corpus["searches"]:
                    search["returned_ids"] = [identifier]
                self.assertTrue(review.corpus_content(self.protocol, corpus))

    def test_removed_freeze_metadata_and_malformed_optional_fields_are_diagnostics(self):
        self.lock()
        del self.protocol["corpus_digest"]
        del self.protocol["corpus_receipt"]
        self.save()
        self.assertTrue(any("references were removed" in item["detail"] for item in self.check()))
        self.corpus["coverage"] = ["malformed"]
        self.save()
        self.assertTrue(self.check())


if __name__ == "__main__":
    unittest.main()
