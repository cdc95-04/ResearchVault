"""Behavioral boundaries for shared maintenance-only validation mechanics."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import _validation_common as common
from scripts import benchmark_retrieval as benchmark
from scripts import semantic_contract as semantic


class ValidationCommonTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="validation-common-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_strict_reader_rejects_ambiguous_or_nonfinite_json_with_old_diagnostic(self):
        path = self.root / "input.json"
        invalid = (b'{"x":1,"x":2}', b'{"nested":{"x":1,"x":2}}',
                   b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}',
                   b'{"x":1e999}', b'\xff', b'{')
        for raw in invalid:
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                with self.assertRaises(common.ContractError) as caught:
                    common.read_json(path)
                self.assertEqual((caught.exception.code, caught.exception.location),
                                 ("INPUT_READ", "input.json"))
        path.write_text('{"text":"研究", "x":1.25, "flag":true}', encoding="utf-8")
        self.assertEqual(common.read_json(path), {"text": "研究", "x": 1.25, "flag": True})
        self.assertIs(semantic.read_json, common.read_json)

    def test_raw_and_text_digests_keep_distinct_line_ending_and_binary_semantics(self):
        lf, crlf = self.root / "lf.txt", self.root / "crlf.txt"
        lf_bytes = "first\nsecond\r研究 \n".encode("utf-8")
        lf.write_bytes(lf_bytes)
        crlf.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))
        self.assertEqual(common.raw_digest(lf), hashlib.sha256(lf_bytes).hexdigest())
        self.assertNotEqual(common.raw_digest(lf), common.raw_digest(crlf))
        self.assertEqual(common.text_digest(lf), common.text_digest(crlf))
        crlf.write_bytes(lf_bytes.replace(b"\r", b"\n"))
        self.assertNotEqual(common.text_digest(lf), common.text_digest(crlf))
        crlf.write_bytes(lf_bytes + b" ")
        self.assertNotEqual(common.text_digest(lf), common.text_digest(crlf))
        crlf.write_bytes(b"\xff\r\n")
        self.assertEqual(common.raw_digest(crlf), hashlib.sha256(b"\xff\r\n").hexdigest())
        with self.assertRaises(UnicodeDecodeError):
            common.text_digest(crlf)
        self.assertIs(benchmark.digest, common.text_digest)

    def test_relative_paths_reject_platform_escapes(self):
        self.assertEqual(common.safe_relative_path(self.root, "folder/fixture.json"),
                         self.root.resolve() / "folder" / "fixture.json")
        for name in (None, "", ".", "..", "../fixture.json", "folder/../fixture.json",
                     "/fixture.json", "C:/fixture.json", "C:fixture.json",
                     "\\fixture.json", "folder\\fixture.json", "//host/share/fixture.json"):
            with self.subTest(name=name), self.assertRaises(common.ContractError) as caught:
                common.safe_relative_path(self.root, name)
            self.assertEqual(caught.exception.code, "FROZEN_PATH")

    def test_shared_inputs_and_numbers_preserve_frozen_observations_without_writes(self):
        freeze = common.read_json(common.GOLDEN / "b2" / "freeze.json")
        before = {name: (common.ROOT / name).read_bytes() for name in freeze["files"]}
        report = common.verify_freeze()
        self.assertTrue(report["valid"])
        self.assertEqual(report["counts"], {"expected_claims": 9, "numerical_expectations": 26,
                                         "retrieval_queries": 6, "deliberate_invalid_cases": 33})
        self.assertEqual(report["checked_files"], len(before))
        self.assertFalse(report["pdf_hashes_checked"])
        self.assertFalse(report["semantic_judgment_performed"])
        self.assertIs(semantic.verify_freeze, common.verify_freeze)
        annotations, captures = common.original_inputs()
        self.assertEqual(set(annotations), set(common.PDF_NAMES))
        for paper_id in common.PDF_NAMES:
            self.assertEqual(annotations[paper_id], common.read_json(
                common.GOLDEN / "annotations" / (paper_id + ".json")))
            self.assertEqual(captures[paper_id], common.read_json(
                common.GOLDEN / "captures" / (paper_id + ".json")))
        comparison = common.read_json(common.GOLDEN / "comparison.json")
        expected = common.read_json(common.GOLDEN / "b2" / "retrieval_results.json")
        self.assertEqual(common.compare_reviewed_numbers(annotations, captures, comparison),
                         expected["numerical_regression"])
        self.assertEqual(benchmark.numeric_regression(), expected["numerical_regression"])
        self.assertEqual(before, {name: (common.ROOT / name).read_bytes() for name in before})

    def test_reviewed_numeric_mapping_still_requires_explanation_and_full_coverage(self):
        annotations, captures = common.original_inputs()
        comparison = common.read_json(common.GOLDEN / "comparison.json")
        for mutation, message in (("reason", "explain conditions"),
                                  ("mapping", "reviewed mapping"),
                                  ("claim", "every claim exactly once")):
            changed = copy.deepcopy(comparison)
            row = next(r for r in changed["records"] if r["numeric_mappings"])
            if mutation == "reason":
                row["numeric_mappings"][0]["mapping_reason"] = " "
            elif mutation == "mapping":
                row["numeric_mappings"].pop()
            else:
                changed["records"].pop()
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, message):
                common.compare_reviewed_numbers(annotations, captures, changed)

    def test_original_inputs_keep_independence_inventory_and_query_target_checks(self):
        for folder in ("annotations", "captures"):
            (self.root / folder).mkdir()
            for paper_id in common.PDF_NAMES:
                name = paper_id + ".json"
                (self.root / folder / name).write_bytes((common.GOLDEN / folder / name).read_bytes())
        path = self.root / "annotations" / "sac2018.json"
        original = common.read_json(path)
        for mutation, message in (("independence", "independence declaration"),
                                  ("inventory", "claim inventories differ"),
                                  ("query", "no valid target")):
            changed = copy.deepcopy(original)
            if mutation == "independence":
                changed["review"]["implementation_outputs_seen"] = True
            elif mutation == "inventory":
                changed["claims"].append(copy.deepcopy(changed["claims"][0]))
            else:
                changed["retrieval_queries"][0]["expected_claim_ids"] = ["missing-claim"]
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, message):
                common.original_inputs(self.root)


if __name__ == "__main__":
    unittest.main()
