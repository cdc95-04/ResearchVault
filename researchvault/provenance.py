"""Finite, content-addressed receipts with explicit revision ancestry.

Receipts attest to bytes recorded locally. They attest to neither trusted time,
scientific correctness nor permission to execute an experiment.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .documents import diagnostic, read_record
from .safety import require_writable


def canonical(value) -> bytes:
    """Encode JSON deterministically, normalizing YAML dates without coercion."""
    active = set()

    def visit(item):
        if isinstance(item, datetime):
            if item.tzinfo is not None:
                item = item.astimezone(timezone.utc)
            return item.isoformat()
        if isinstance(item, date):
            return item.isoformat()
        if item is None or isinstance(item, (str, bool, int)):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("nonfinite number cannot enter a receipt")
            return item
        if not isinstance(item, (dict, list)):
            raise ValueError(f"unsupported JSON value: {type(item).__name__}")
        marker = id(item)
        if marker in active:
            raise ValueError("recursive value cannot enter a receipt")
        active.add(marker)
        try:
            if isinstance(item, dict):
                if not all(isinstance(key, str) for key in item):
                    raise ValueError("JSON mapping keys must be strings")
                return {key: visit(child) for key, child in item.items()}
            return [visit(child) for child in item]
        finally:
            active.remove(marker)

    return json.dumps(visit(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def receipt_directory(settings, kind, object_id) -> Path:
    if not isinstance(kind, str) or not re.fullmatch(r"[a-z][a-z-]*", kind):
        raise ValueError("invalid receipt kind")
    if not isinstance(object_id, str) or not object_id.strip():
        raise ValueError("a stable object identifier is required")
    path = settings.folder("metadata") / "receipts" / kind / digest(object_id)
    return settings.resolve(settings.relative(path))


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate receipt key: {key}")
        result[key] = value
    return result


def read_receipt(settings, path) -> dict:
    path = settings.resolve(str(path))
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs)
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        raise ValueError("receipt must be a schema 2 object")
    required = {"kind", "object_id", "source", "snapshot", "snapshot_digest",
                "created_at", "previous", "reason", "timing", "receipt_digest"}
    if not required.issubset(data):
        raise ValueError("receipt is missing envelope fields")
    if not isinstance(data["snapshot"], dict):
        raise ValueError("receipt snapshot must be a mapping")
    if data["snapshot_digest"] != digest(data["snapshot"]):
        raise ValueError("receipt snapshot digest mismatch")
    envelope = {key: value for key, value in data.items() if key != "receipt_digest"}
    if data["receipt_digest"] != digest(envelope):
        raise ValueError("receipt envelope digest mismatch")
    expected = receipt_directory(settings, data["kind"], data["object_id"]) / (data["snapshot_digest"] + ".json")
    if path != expected:
        raise ValueError("receipt identity does not match its storage path")
    moment = datetime.fromisoformat(data["created_at"])
    if moment.tzinfo is None:
        raise ValueError("receipt time must include a timezone")
    if data["timing"] not in {"pre-result", "post-result", "recorded"}:
        raise ValueError("invalid receipt timing")
    settings.resolve(data["source"])
    return data


def history(settings, kind, object_id) -> list[dict]:
    """Validate the whole chain independently of references on a human page."""
    directory = receipt_directory(settings, kind, object_id)
    receipts = [read_receipt(settings, settings.relative(path))
                for path in sorted(directory.glob("*.json"))]
    if not receipts:
        return []
    by_digest = {item["snapshot_digest"]: item for item in receipts}
    roots = [item for item in receipts if item["previous"] is None]
    if len(roots) != 1 or len(by_digest) != len(receipts):
        raise ValueError("receipt history has duplicate identities or multiple roots")
    ordered = [roots[0]]
    while len(ordered) < len(receipts):
        next_items = [item for item in receipts
                      if item["previous"] == ordered[-1]["snapshot_digest"]]
        if len(next_items) != 1 or next_items[0] in ordered:
            raise ValueError("receipt history is branched, disconnected or cyclic")
        if not isinstance(next_items[0]["reason"], str) or not next_items[0]["reason"].strip():
            raise ValueError("revision receipt lacks a reason")
        ordered.append(next_items[0])
    return ordered


def create_receipt(settings, *, kind, object_id, source, content, apply=False,
                   previous=None, reason=None, timing="recorded") -> dict:
    """Prepare all bytes before any mutation; create the receipt exclusively."""
    if apply:
        require_writable(settings, 'Provenance receipt creation')
    if not isinstance(content, dict):
        raise ValueError("receipt snapshot must be a mapping")
    # This also validates unsupported/recursive values before creating directories.
    snapshot_digest = digest(content)
    if timing not in {"pre-result", "post-result", "recorded"}:
        raise ValueError("invalid revision timing")
    source = settings.relative(settings.resolve(str(source)))
    directory = receipt_directory(settings, kind, object_id)
    receipts = history(settings, kind, object_id)
    existing = next((item for item in receipts if item["snapshot_digest"] == snapshot_digest), None)
    path = directory / (snapshot_digest + ".json")
    if existing is not None:
        # A historical snapshot may be inspected, but cannot replace the chain tip.
        if existing != receipts[-1]:
            raise ValueError("snapshot is historical; reverting requires a new explicit revision")
        return {"digest": snapshot_digest, "receipt": settings.relative(path),
                "applied": path.exists(), "existing": True, "envelope": existing}
    if receipts:
        if previous != receipts[-1]["snapshot_digest"]:
            raise ValueError("revision must name the existing latest predecessor")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("revision requires a nonempty reason")
        if kind in {"claim", "design"} and receipts[-1]["timing"] == "post-result" and timing != "post-result":
            raise ValueError("post-result lineage cannot become pre-result again")
    elif previous is not None:
        raise ValueError("predecessor does not exist")
    envelope = {"schema_version": 2, "kind": kind, "object_id": object_id,
                "source": source, "snapshot": content, "snapshot_digest": snapshot_digest,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "previous": previous, "reason": reason, "timing": timing}
    envelope["receipt_digest"] = digest(envelope)
    payload = canonical(envelope) + b"\n"
    if apply:
        directory.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload)
    return {"digest": snapshot_digest, "receipt": settings.relative(path),
            "applied": bool(apply), "existing": False, "envelope": envelope}


def artifact(settings, path) -> dict:
    if not isinstance(path, str) or not path:
        raise ValueError("artifact path must be a nonempty string")
    target = settings.resolve(path)
    if not target.is_file():
        raise ValueError(f"artifact does not exist: {path}")
    return {"path": settings.relative(target),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def _page_content(record):
    data = {key: value for key, value in record.data.items()
            if key not in {"provenance_digest", "provenance_receipt"}}
    return {"data": data, "body": record.body}


def snapshot(settings, path, inputs=(), sources=(), tool_version=None, apply=False,
             previous=None, reason=None):
    if apply:
        require_writable(settings, 'Provenance snapshot')
    record = read_record(settings.resolve(str(path)), settings.vault)
    if not isinstance(inputs, (list, tuple)) or not isinstance(sources, (list, tuple)):
        raise ValueError("snapshot inputs and sources must be path sequences")
    ids = [record.data.get(key) for key in ("card_id", "experiment_id", "trial_id", "result_id",
            "review_id", "gap_id", "hypothesis_id", "question_id", "idea_id", "claim_id", "record_id")]
    object_id = next((value for value in ids if isinstance(value, str) and value), record.relative)
    content = {"page": _page_content(record), "inputs": [artifact(settings, p) for p in inputs],
               "sources": [artifact(settings, p) for p in sources], "tool_version": tool_version}
    result = create_receipt(settings, kind="provenance", object_id=object_id,
                            source=record.relative, content=content, apply=apply,
                            previous=previous, reason=reason)
    result["metadata"] = {"provenance_digest": result["digest"],
                          "provenance_receipt": result["receipt"]}
    return result


def check(settings, records):
    issues = []
    root = settings.folder("metadata") / "receipts"
    seen = set()
    if root.exists():
        for path in sorted(root.glob("*/*/*.json")):
            relative = "Vault receipt"
            try:
                relative = settings.relative(path)
                receipt = read_receipt(settings, relative)
                key = receipt["kind"], receipt["object_id"]
                if key not in seen:
                    history(settings, *key)
                    seen.add(key)
                if receipt["kind"] == "provenance":
                    for group in ("inputs", "sources"):
                        values = receipt["snapshot"].get(group, [])
                        if not isinstance(values, list):
                            raise ValueError("snapshot artifact collection must be a list")
                        for value in values:
                            if not isinstance(value, dict) or artifact(settings, value["path"]) != value:
                                raise ValueError("snapshot artifact changed or is malformed")
            except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
                issues.append(diagnostic("provenance.receipt", relative, str(exc)))
    for record in records:
        data = record.data
        if not data.get("provenance_digest") and not data.get("provenance_receipt"):
            continue
        try:
            receipt = read_receipt(settings, data["provenance_receipt"])
            if receipt["kind"] != "provenance" or receipt["snapshot_digest"] != data["provenance_digest"]:
                raise ValueError("page references a different provenance receipt")
            if digest(receipt["snapshot"]["page"]) != digest(_page_content(record)):
                raise ValueError("page has changed since its provenance snapshot")
        except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
            issues.append(diagnostic("provenance.page", record.relative, str(exc)))
    return issues
