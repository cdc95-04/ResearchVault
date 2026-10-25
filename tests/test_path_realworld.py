"""Real filesystem behavior using only disposable, explicitly synthetic data."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from researchvault.acquisition import run
from researchvault.config import REPOSITORY, contained, load_settings
from researchvault.documents import read_record, write_new
from researchvault.validation import validate


class RealWorldPaths(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ResearchVault paths ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("RESEARCHVAULT_CONFIG", None)
        self.vault = self.base / "合成 笔记库"
        self.vault.mkdir()
        self.settings = load_settings(vault=self.vault, synthetic=True, cwd=self.base)
        self.settings.options["read_only"] = True

    def directory_link(self, link, target):
        """Exercise symlinks, or Windows junctions without elevation."""
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("Host cannot create a directory symlink")
            environment = dict(os.environ, RV_TEST_LINK=str(link), RV_TEST_TARGET=str(target))
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "New-Item -ItemType Junction -Path $env:RV_TEST_LINK "
                 "-Target $env:RV_TEST_TARGET -ErrorAction Stop | Out-Null"],
                env=environment, capture_output=True, text=True,
            )
            if result.returncode:
                self.skipTest("Host cannot create a symlink or Windows junction")
        self.assertEqual(link.resolve(), target.resolve())
        # Remove the link itself before TemporaryDirectory cleanup; never its target.
        def remove_link():
            if link.is_symlink():
                link.unlink()
            elif link.exists():
                link.rmdir()
        self.addCleanup(remove_link)

    def record(self, relative, body="Synthetic body.\n"):
        target = self.vault / relative
        write_new(target, {"type": "concept", "schema_version": 2}, body)
        return target

    def assert_private_paths_absent(self, result):
        rendered = json.dumps(result, ensure_ascii=False)
        for path in (self.base, self.vault):
            self.assertNotIn(str(path), rendered)
            self.assertNotIn(json.dumps(str(path))[1:-1], rendered)

    def test_nested_cjk_spaces_and_markdown_link_are_read_without_changes(self):
        first = self.record("研究 文件/已有 记录.md", "See [source](<相关 材料.md>).\n")
        second = self.record("研究 文件/相关 材料.md", "精确的合成文本。\r\n")
        before = {path: path.read_bytes() for path in (first, second)}
        result = validate(self.settings)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["records"], 2)
        self.assertEqual(read_record(second, self.vault).body, "精确的合成文本。\r\n")
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_existing_nested_path_longer_than_260_characters_is_read(self):
        relative = Path(*(["synthetic long 路径 " + "x" * 20] * 7)) / "研究 note.md"
        try:
            target = self.record(relative)
        except OSError as exc:
            if getattr(exc, "winerror", None) in (3, 206) or exc.errno == 36:
                self.skipTest("Host filesystem does not support this long path")
            raise
        self.assertGreater(len(str(target)), 260)
        before = target.read_bytes()
        self.assertEqual(read_record(target, self.vault).relative, relative.as_posix())
        self.assertTrue(validate(self.settings)["valid"])
        self.assertEqual(target.read_bytes(), before)

    @unittest.skipUnless(os.name == "nt", "Windows extended namespace spelling")
    def test_extended_namespace_cannot_bypass_repository_data_boundary(self):
        extended = "\\\\?\\" + str(REPOSITORY / "private")
        with self.assertRaises(ValueError):
            load_settings(vault=extended, cwd=self.base)

    def test_directory_link_escape_rejected_before_record_read(self):
        outside = self.base / "外部 合成源"
        outside.mkdir()
        write_new(outside / "external.md", {"type": "concept", "schema_version": 2}, "Outside marker.")
        link = self.vault / "linked folder"
        self.directory_link(link, outside)
        with self.assertRaisesRegex(ValueError, "escapes"):
            contained(self.vault, "linked folder/external.md")
        with self.assertRaisesRegex(ValueError, "outside"):
            read_record(link / "external.md", self.vault)

    def test_inside_directory_link_preserves_resolved_record_identity(self):
        target = self.record("actual 文件/source.md")
        link = self.vault / "alias 文件"
        self.directory_link(link, target.parent)
        record = read_record(link / target.name, self.vault)
        self.assertEqual(record.path, target.resolve())
        self.assertEqual(record.relative, "actual 文件/source.md")

    def test_acquisition_intake_link_cannot_write_outside_runtime(self):
        runtime, outside = self.base / "runtime", self.base / "outside"
        runtime.mkdir()
        outside.mkdir()
        sentinel = outside / "unchanged.txt"
        sentinel.write_bytes(b"Synthetic untouched source")
        self.directory_link(runtime / "intake", outside)
        self.settings.runtime = runtime
        self.settings.options["read_only"] = False
        with self.assertRaises(ValueError):
            run(self.settings, [], selected=[], enabled=True)
        self.assertEqual(list(outside.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"Synthetic untouched source")

    def test_receipt_link_escape_is_a_diagnostic_not_an_uncaught_exception(self):
        outside = self.base / "external receipts"
        outside.mkdir()
        receipt = outside / "synthetic.json"
        receipt.write_text("This external synthetic file must not be parsed.", encoding="utf-8")
        link = self.vault / ".meta" / "receipts" / "provenance" / "linked-id"
        self.directory_link(link, outside)
        result = validate(self.settings)
        self.assertIn("provenance.receipt", {row["code"] for row in result["diagnostics"]})
        self.assert_private_paths_absent(result)
        self.assertEqual(receipt.read_text(encoding="utf-8"), "This external synthetic file must not be parsed.")

    def test_readonly_missing_vault_diagnostic_withholds_absolute_path(self):
        self.settings.vault = self.base / "missing synthetic vault"
        result = validate(self.settings)
        self.assertEqual(result["diagnostics"][0]["code"], "VAULT_MISSING")
        self.assert_private_paths_absent(result)

    def test_readonly_invalid_claim_diagnostic_withholds_absolute_path(self):
        target = self.vault / ".meta" / "claims" / "bad.yaml"
        target.parent.mkdir(parents=True)
        target.write_text("claim_id: ''\n", encoding="utf-8")
        result = validate(self.settings)
        self.assertIn("INVALID_CLAIM", {row["code"] for row in result["diagnostics"]})
        self.assert_private_paths_absent(result)

    def test_readonly_yaml_diagnostic_does_not_copy_source_content(self):
        marker = "synthetic-private-detail-marker"
        target = self.vault / "invalid.md"
        target.write_text("---\ntype: concept\nsecret: [" + marker + "\n---\n", encoding="utf-8")
        result = validate(self.settings)
        self.assertIn("INVALID_RECORD", {row["code"] for row in result["diagnostics"]})
        self.assertNotIn(marker, json.dumps(result))

    def test_readonly_broken_external_link_withholds_absolute_path(self):
        self.record("link.md", "[missing](<" + str(self.base / "private missing.md") + ">)\n")
        result = validate(self.settings)
        self.assertIn("BROKEN_LINK", {row["code"] for row in result["diagnostics"]})
        self.assert_private_paths_absent(result)

    def test_default_mode_keeps_existing_diagnostic_details(self):
        self.settings.options["read_only"] = False
        self.record("link.md", "[missing](missing-synthetic-source.md)\n")
        result = validate(self.settings)
        issue = next(row for row in result["diagnostics"] if row["code"] == "BROKEN_LINK")
        self.assertEqual(issue["detail"], "missing-synthetic-source.md")


if __name__ == "__main__":
    unittest.main()
