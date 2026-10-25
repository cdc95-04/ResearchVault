"""Packaging regressions preserve canonical resources and deterministic boundaries."""
from importlib import metadata
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import audit_plugin
from scripts import audit_repository


class PluginPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="researchvault-plugin-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Only ephemeral public package resources, never real Zotero or Vault data.
        for directory in ("skills", "references", "templates"):
            shutil.copytree(audit_plugin.ROOT / directory, self.root / directory)
        shutil.copyfile(audit_plugin.ROOT / "pyproject.toml", self.root / "pyproject.toml")
        shutil.copyfile(audit_plugin.ROOT / "LICENSE", self.root / "LICENSE")
        self.manifest = {"$schema": audit_plugin.SCHEMA, "name": "researchvault",
                         "version": metadata.version("researchvault"),
                         "description": audit_plugin.DESCRIPTION,
                         "repository": "https://github.com/cdc95-04/ResearchVault-release"}
        self.save_manifest()

    def save_manifest(self):
        (self.root / "plugin.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def check(self):
        return audit_plugin.check_package(self.root)

    def test_canonical_package_has_twelve_roles_shared_resources_and_all_links(self):
        report = self.check()
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual((report["skills"], report["references"], report["templates"],
                          report["skill_local_links"]), (12, 5, 22, 39))
        self.assertEqual(report["plugin_version"], report["project_version"])
        self.assertEqual(report["plugin_version"], report["installed_version"])
        self.assertFalse(report["compatibility_overlay"])

    def test_manifest_and_installed_release_drift_are_detected_independently(self):
        drift = self.manifest["version"] + "-drift"
        self.manifest["version"] = drift
        self.save_manifest()
        self.assertIn("versions must agree", " ".join(self.check()["errors"]))
        self.manifest["version"] = metadata.version("researchvault")
        self.save_manifest()
        with patch.object(audit_plugin.metadata, "version", return_value=drift):
            self.assertIn("versions must agree", " ".join(self.check()["errors"]))
        path = self.root / "pyproject.toml"
        path.write_text(path.read_text(encoding="utf-8").replace(
            'version = "' + self.manifest["version"] + '"', 'version = "' + drift + '"'), encoding="utf-8")
        self.assertIn("versions must agree", " ".join(self.check()["errors"]))

    def test_missing_or_malformed_manifest_never_becomes_a_valid_package(self):
        path = self.root / "plugin.json"
        path.unlink()
        self.assertFalse(self.check()["valid"])
        for payload in (b"{", b"[]", b"{}", b'{"name":"researchvault","name":"other"}',
                        b'{"version":NaN}', b"\xff"):
            with self.subTest(payload=payload):
                path.write_bytes(payload)
                report = self.check()
                self.assertFalse(report["valid"])
                self.assertIn("plugin.json", " ".join(report["errors"]))
        self.save_manifest()
        self.manifest["name"] = "other"
        self.save_manifest()
        self.assertIn("Unexpected manifest name", self.check()["errors"])

    def test_inventory_and_frontmatter_failures_are_actionable(self):
        skill = self.root / "skills" / "paper-note-writer" / "SKILL.md"
        original = skill.read_bytes()
        skill.write_text("---\nname: wrong\ndescription: ''\n---\n", encoding="utf-8")
        self.assertIn("Invalid Skill frontmatter", " ".join(self.check()["errors"]))
        skill.write_bytes(original)
        skill.unlink()
        self.assertIn("twelve specified roles", " ".join(self.check()["errors"]))
        skill.write_bytes(original)
        extra = self.root / "skills" / "new-role" / "SKILL.md"
        extra.parent.mkdir()
        extra.write_bytes(original)
        self.assertIn("twelve specified roles", " ".join(self.check()["errors"]))
        extra.unlink()
        (self.root / "references" / "evidence.md").unlink()
        report = self.check()
        self.assertIn("canonical root references", " ".join(report["errors"]))
        self.assertIn("Missing/escaping local Skill resource", " ".join(report["errors"]))

    def test_local_links_reject_missing_and_cross_platform_escapes(self):
        skill = self.root / "skills" / "paper-note-writer" / "SKILL.md"
        original = skill.read_text(encoding="utf-8")
        for target in ("../../references/missing.md", "../../../outside.md",
                       "../../../%6futside.md", "/outside.md", "Z:/outside.md",
                       "Z:outside.md", r"..\..\references\evidence.md"):
            with self.subTest(target=target):
                skill.write_text(original + "\n[resource](" + target + ")\n", encoding="utf-8")
                self.assertIn("Missing/escaping local Skill resource", " ".join(self.check()["errors"]))

    def test_shared_resource_copies_are_rejected(self):
        directory = self.root / "skills" / "paper-note-writer" / "references"
        directory.mkdir()
        shutil.copyfile(self.root / "references" / "evidence.md", directory / "evidence.md")
        self.assertIn("must not be copied into Skills", " ".join(self.check()["errors"]))
        shutil.rmtree(directory)
        directory = self.root / "plugin" / "references"
        directory.mkdir(parents=True)
        self.assertIn("Duplicate references directory", " ".join(self.check()["errors"]))

    def test_optional_overlay_cannot_conflict_or_add_prohibited_capabilities(self):
        directory = self.root / ".codex-plugin"
        directory.mkdir()
        path = directory / "plugin.json"
        path.write_text(json.dumps({"name": "researchvault", "version": self.manifest["version"] + "-drift"}), encoding="utf-8")
        self.assertIn("conflicts with portable version", " ".join(self.check()["errors"]))
        path.write_text(json.dumps({"name": "researchvault", "version": self.manifest["version"],
                                   "description": self.manifest["description"]}), encoding="utf-8")
        self.assertTrue(self.check()["valid"])
        self.manifest["extensions"] = {"com.openai": {"mcpServers": {"unexpected": {}}}}
        self.save_manifest()
        self.assertIn("must not configure MCP", " ".join(self.check()["errors"]))
        self.manifest.pop("extensions")
        self.save_manifest()
        for name in ("mcp.json", ".mcp.json", "hooks.json", ".app.json"):
            with self.subTest(name=name):
                resource = self.root / name
                resource.write_text("{}", encoding="utf-8")
                self.assertFalse(self.check()["valid"])
                resource.unlink()
        self.manifest["license"] = "MIT"
        self.save_manifest()
        self.assertIn("minimal ResearchVault fields", " ".join(self.check()["errors"]))

    def test_package_requires_complete_mit_license_and_project_copyright(self):
        path = self.root / "LICENSE"
        original = path.read_text(encoding="utf-8")
        self.assertTrue(self.check()["valid"])
        path.unlink()
        self.assertIn("license", " ".join(self.check()["errors"]).lower())
        for payload in (
                b"", b"MIT License", b"\xff",
                original.replace("Copyright (c) 2026 cdc95-04", "Copyright (c) 2026 other").encode(),
                original.replace("Permission is hereby granted, free of charge,", "").encode(),
                original.replace("The above copyright notice and this permission notice shall be included in all", "").encode(),
                original.replace('THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR', "").encode()):
            with self.subTest(payload=payload):
                path.write_bytes(payload)
                report = self.check()
                self.assertFalse(report["valid"])
                self.assertIn("license", " ".join(report["errors"]).lower())
        path.write_text(original, encoding="utf-8")
        self.assertTrue(self.check()["valid"])

    def test_plugin_audit_retains_repository_pdf_private_secret_and_license_gate(self):
        hygiene = {"valid": False, "errors": ["Private/runtime artifact: fixture.pdf",
                   "Possible credential or machine-specific path: fixture.txt",
                   "Missing MIT license declaration"]}
        with patch.object(audit_plugin, "ROOT", self.root), \
                patch.object(audit_repository, "audit", return_value=hygiene) as repository_audit:
            report = audit_plugin.audit()
        repository_audit.assert_called_once_with()
        self.assertTrue(report["package"]["valid"])
        self.assertFalse(report["valid"])
        self.assertEqual(report["errors"], hygiene["errors"])


if __name__ == "__main__":
    unittest.main()
