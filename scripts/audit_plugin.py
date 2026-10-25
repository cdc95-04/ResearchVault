"""Mechanical ResearchVault package checks; no activation or scientific judgment."""
from __future__ import annotations

from importlib import metadata
from pathlib import Path, PureWindowsPath
import json
import re
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from researchvault.documents import read_record
from scripts import _validation_common as common
from scripts import audit_repository

SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
DESCRIPTION = "Research evidence, literature, scientific reasoning and experiment workflow skills."
PROHIBITED_KEYS = {"mcpServers", "mcp", "hooks", "apps", "app", "ui"}


def project_version(path):
    """Read this project's static quoted release field without a Python 3.11 dependency."""
    text = path.read_text(encoding="utf-8")
    sections = re.findall(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", text)
    versions = re.findall(r'^\s*version\s*=\s*"([^"\r\n]+)"\s*(?:#.*)?$',
                          sections[0] if len(sections) == 1 else "", re.M)
    if len(versions) != 1:
        raise ValueError("Expected one static quoted [project] version in pyproject.toml")
    return versions[0]


def _prohibited_fields(value):
    if isinstance(value, dict):
        return any(key in PROHIBITED_KEYS or _prohibited_fields(child)
                   for key, child in value.items())
    if isinstance(value, list):
        return any(_prohibited_fields(child) for child in value)
    return False


def check_package(root):
    """Inspect the explicit package root; repository hygiene remains a separate gate."""
    root = Path(root).resolve()
    errors, manifest = [], {}
    manifest_path = root / "plugin.json"
    try:
        if not manifest_path.resolve().is_relative_to(root):
            raise ValueError("Manifest escapes the plugin root")
        manifest = common.read_json(manifest_path)
        if not isinstance(manifest, dict):
            raise ValueError("Manifest must be a JSON object")
    except (OSError, ValueError) as exc:
        errors.append("Invalid root plugin.json: " + str(exc))
        manifest = {}
    if manifest:
        if set(manifest) != {"$schema", "name", "version", "description", "repository"}:
            errors.append("Portable manifest must retain the minimal ResearchVault fields")
        for key, expected in (("$schema", SCHEMA), ("name", "researchvault"),
                              ("description", DESCRIPTION),
                              ("repository", "https://github.com/cdc95-04/ResearchVault")):
            if manifest.get(key) != expected:
                errors.append("Unexpected manifest " + key)
        if _prohibited_fields(manifest):
            errors.append("Manifest must not configure MCP, hooks or apps/UI")
    else:
        errors.append("Root plugin.json must declare the portable plugin identity")
    release, installed = None, None
    try:
        release = project_version(root / "pyproject.toml")
        installed = metadata.version("researchvault")
        if manifest.get("version") != release or installed != release:
            errors.append("Plugin, pyproject and installed ResearchVault versions must agree")
    except (OSError, ValueError, metadata.PackageNotFoundError) as exc:
        errors.append("Release version unavailable: " + str(exc))

    overlay_path = root / ".codex-plugin" / "plugin.json"
    if overlay_path.exists():
        try:
            if not overlay_path.resolve().is_relative_to(root):
                raise ValueError("Compatibility manifest escapes the plugin root")
            overlay = common.read_json(overlay_path)
            if not isinstance(overlay, dict):
                raise ValueError("Compatibility manifest must be a JSON object")
            for key in ("name", "version", "description"):
                if key in overlay and overlay[key] != manifest.get(key):
                    errors.append("Compatibility manifest conflicts with portable " + key)
            if _prohibited_fields(overlay):
                errors.append("Compatibility manifest must not configure MCP, hooks or apps/UI")
        except (OSError, ValueError) as exc:
            errors.append("Invalid compatibility manifest: " + str(exc))

    skills_root = root / "skills"
    paths = sorted(skills_root.rglob("SKILL.md"))
    actual = {p.parent.name for p in paths if len(p.relative_to(skills_root).parts) == 2}
    if actual != audit_repository.SKILLS or len(paths) != len(audit_repository.SKILLS):
        errors.append("Canonical Skill inventory must equal the twelve specified roles")
    links = 0
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            record = read_record(path, root)
            if (record.data.get("name") != path.parent.name
                    or not isinstance(record.data.get("description"), str)
                    or not record.data["description"].strip()):
                errors.append("Invalid Skill frontmatter: " + relative)
            for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", record.body):
                target = unquote(target.strip("<>").split("#", 1)[0])
                if not target:
                    continue
                if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) and not PureWindowsPath(target).drive:
                    continue
                links += 1
                resolved = (path.parent / target).resolve()
                if ("\\" in target or PureWindowsPath(target).drive
                        or not resolved.is_relative_to(root) or not resolved.is_file()):
                    errors.append("Missing/escaping local Skill resource: " + relative + " -> " + target)
        except (OSError, ValueError) as exc:
            errors.append("Invalid Skill resource: " + relative + ": " + str(exc))

    resource_counts, resource_names = {}, set()
    for directory, expected_count in (("references", 5), ("templates", 22)):
        base = root / directory
        resources = list(base.rglob("*"))
        files = [p for p in resources if p.is_file()]
        resource_counts[directory] = len(files)
        resource_names.update(p.name for p in files)
        if (len(files) != expected_count or any(p.parent != base for p in resources)
                or any(not p.resolve().is_relative_to(root) for p in resources)):
            errors.append("Expected only canonical root " + directory + " resources")
        if any(path != base for path in root.glob("*/" + directory)):
            errors.append("Duplicate " + directory + " directory outside the canonical root")
    if any(path.name in resource_names for path in skills_root.rglob("*") if path.is_file()):
        errors.append("Shared references/templates must not be copied into Skills")
    if any(path != skills_root for path in root.glob("*/skills")):
        errors.append("Duplicate Skills directory outside the canonical root")
    for name in ("mcp.json", ".mcp.json", "hooks", "hooks.json", "apps", ".app.json"):
        if (root / name).exists() or (root / ".codex-plugin" / name).exists():
            errors.append("Prohibited plugin resource: " + name)
    errors.extend(audit_repository.check_mit_license(root))
    return {"valid": not errors, "canonical_entrypoint": "plugin.json",
            "plugin_version": manifest.get("version"), "project_version": release,
            "installed_version": installed, "skills": len(actual),
            "references": resource_counts["references"], "templates": resource_counts["templates"],
            "skill_local_links": links, "compatibility_overlay": overlay_path.exists(), "errors": errors}


def audit():
    package = check_package(ROOT)
    repository = audit_repository.audit()
    errors = package["errors"] + repository["errors"]
    return {"valid": not errors, "package": package, "repository": repository, "errors": errors,
            "limits": "Mechanical package checks and existing heuristic repository hygiene only; "
                      "not a complete remote JSON Schema validator, activation test, secret guarantee "
                      "or scientific/human review."}


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["valid"] else 1)
