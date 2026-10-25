"""Shared file and fixture mechanics for the current offline validation scripts.

The frozen ``validate_golden.py`` is an immutable historical execution entry
point. Current maintenance scripts share these mechanics instead of importing
that runner. This module reads explicit records; it never judges scientific
prose, calls a semantic backend, or rewrites evidence and reviewed mappings.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re


ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "validation" / "golden"
PDF_NAMES = {"sac2018": "sac2018.pdf",
             "diffusion_policy2023": "diffusion_policy2023_rss.pdf",
             "sim2real2018": "sim2real2018_arxiv_v3.pdf"}
COUNTS = {"expected_claims": 9, "numerical_expectations": 26,
          "retrieval_queries": 6, "deliberate_invalid_cases": 33}


class ContractError(ValueError):
    def __init__(self, code, location, message):
        super().__init__(message)
        self.code, self.location, self.message = code, location, message


def _require(condition, code, location, message):
    if not condition:
        raise ContractError(code, location, message)


def raw_digest(path):
    """SHA-256 of exact file bytes, including line endings and binary data."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_digest(path):
    """SHA-256 of UTF-8 file bytes with CRLF changed to LF, nothing else."""
    raw = Path(path).read_bytes()
    raw.decode("utf-8")  # Text digests must not silently accept a binary input.
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def read_json(path):
    """Read strict UTF-8 JSON; retain the semantic contract's input diagnostic."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Nonfinite JSON number")
        return result

    def constant(value):
        raise ValueError("Nonfinite JSON constant")

    try:
        return json.loads(Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=pairs, parse_float=number, parse_constant=constant)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ContractError("INPUT_READ", Path(path).name,
                            "Input is missing or is not strict UTF-8 JSON") from exc


def _object(value, location):
    _require(isinstance(value, dict), "OBJECT", location, "Expected an object")
    return value


def _list(value, location):
    _require(isinstance(value, list), "LIST", location, "Expected an array")
    return value


def _text(value, location):
    _require(isinstance(value, str) and bool(value.strip()), "TEXT", location,
             "Expected nonempty explanatory text")


def _sha(value, location):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
             "DIGEST", location, "Expected a lowercase SHA-256 digest")


def safe_relative_path(root, name):
    """Resolve a portable relative path without traversal or drive escapes."""
    _require(isinstance(name, str) and "\\" not in name, "FROZEN_PATH", "freeze",
             "Frozen file paths must be portable relative paths")
    parts = PurePosixPath(name)
    _require(not parts.is_absolute() and not PureWindowsPath(name).drive and
             ".." not in parts.parts and bool(parts.parts),
             "FROZEN_PATH", "freeze", "Frozen path escapes its repository")
    root = Path(root).resolve()
    resolved = (root / name).resolve()
    _require(resolved.is_relative_to(root), "FROZEN_PATH", "freeze",
             "Frozen path escapes its repository")
    return resolved


def _inventory(rows, field, location):
    result = {}
    for row in _list(rows, location):
        _object(row, location)
        key = row.get(field)
        _text(key, location + "." + field)
        _require(key not in result, "DUPLICATE_CASE", location,
                 "Inventories must contain each identity exactly once")
        result[key] = row
    return result


def verify_freeze(repo_root=ROOT, *, papers_dir=None):
    """Check frozen bytes and original inventory; raise ValueError on failure."""
    root = Path(repo_root).resolve()
    golden = root / "validation" / "golden"
    freeze = _object(read_json(golden / "b2" / "freeze.json"), "freeze")
    _require(freeze.get("human_review_status") == "pending", "HUMAN_STATUS",
             "freeze", "The frozen baseline remains pending human review")
    files = _object(freeze.get("files"), "freeze.files")
    required = {"scripts/validate_golden.py", "validation/golden/comparison.json",
        "validation/golden/comparison.review.md", "validation/golden/reports/observed.json"}
    for paper_id in PDF_NAMES:
        required.update({f"validation/golden/annotations/{paper_id}.json",
            f"validation/golden/annotations/{paper_id}.review.md",
            f"validation/golden/captures/{paper_id}.json"})
    _require(set(files) == required, "FROZEN_INVENTORY", "freeze.files",
             "Freeze must retain the complete original file inventory")
    for name, expected in files.items():
        _sha(expected, name)
        try:
            actual = text_digest(safe_relative_path(root, name))
        except (OSError, UnicodeError) as exc:
            raise ContractError("FROZEN_FILE", name, "Frozen text cannot be read") from exc
        _require(actual == expected, "STALE_FROZEN_FILE", name,
                 "Frozen text differs after LF normalization")
    papers = _inventory(freeze.get("papers"), "paper_id", "freeze.papers")
    _require(set(papers) == set(PDF_NAMES), "PAPER_INVENTORY", "freeze.papers",
             "Freeze must identify the three original source papers")
    counts = {key: 0 for key in COUNTS}
    for paper_id, paper in papers.items():
        _sha(paper.get("pdf_sha256"), paper_id)
        _require(type(paper.get("pdf_pages")) is int and paper["pdf_pages"] > 0,
                 "PAGE_BOUNDS", paper_id, "PDF page bounds must be positive integers")
        annotation = _object(read_json(golden / "annotations" / (paper_id + ".json")), paper_id)
        capture = _object(read_json(golden / "captures" / (paper_id + ".json")), paper_id)
        _require(annotation.get("paper_id") == capture.get("paper_id") == paper_id,
                 "PAPER_ID", paper_id, "Paper filenames and identities disagree")
        annotated = _inventory(annotation.get("claims"), "id", paper_id + ".annotations")
        captured = _inventory(capture.get("claims"), "id", paper_id + ".captures")
        _require(set(annotated) == set(captured), "CLAIM_INVENTORY", paper_id,
                 "Frozen annotation and capture claim identities differ")
        _require(annotation.get("pdf_sha256") == paper["pdf_sha256"] and
                 annotation.get("pdf_pages") == paper["pdf_pages"], "PDF_IDENTITY",
                 paper_id, "Annotation and freeze refer to different PDFs")
        counts["expected_claims"] += len(annotated)
        counts["numerical_expectations"] += sum(len(_list(c.get("numeric_facts"),
            paper_id + ".numeric_facts")) for c in annotated.values())
        counts["retrieval_queries"] += len(_list(annotation.get("retrieval_queries"),
                                                paper_id + ".queries"))
    observed = _object(read_json(golden / "reports" / "observed.json"), "observed")
    injections = _list(observed.get("injections"), "observed.injections")
    counts["deliberate_invalid_cases"] = len(injections)
    _require(counts == freeze.get("counts") == COUNTS, "BASELINE_COUNTS", "freeze.counts",
             "Original 9 claims, 26 numbers, 6 queries and 33 invalid cases must remain")
    _require(canonical_digest(injections) == freeze.get("invalid_cases_digest"),
             "INVALID_CASE_DIGEST", "observed.injections", "Original invalid cases changed")
    if papers_dir is not None:
        for paper_id, name in PDF_NAMES.items():
            path = Path(papers_dir) / name
            try:
                digest = raw_digest(path)
            except OSError as exc:
                raise ContractError("PDF_READ", paper_id, "Explicit source PDF is missing") from exc
            _require(digest == papers[paper_id]["pdf_sha256"], "PDF_DIGEST", paper_id,
                     "Explicit PDF bytes differ from the frozen source")
            try:
                from pypdf import PdfReader
                pages = len(PdfReader(path).pages)
            except (ImportError, OSError, ValueError) as exc:
                raise ContractError("PDF_READ", paper_id, "Explicit PDF page count cannot be read") from exc
            _require(pages == papers[paper_id]["pdf_pages"], "PAGE_BOUNDS", paper_id,
                     "Explicit PDF page count differs from the frozen source")
    return {"valid": True, "checked_files": len(files), "counts": counts,
        "pdf_hashes_checked": papers_dir is not None, "semantic_judgment_performed": False}


def original_inputs(root=GOLDEN):
    """Read original annotations and captures, retaining independence checks."""
    root = Path(root)
    annotations, captures = {}, {}
    for paper_id in PDF_NAMES:
        annotation = read_json(root / "annotations" / (paper_id + ".json"))
        capture = read_json(root / "captures" / (paper_id + ".json"))
        if annotation["paper_id"] != paper_id or capture["paper_id"] != paper_id:
            raise ValueError("Paper identity differs from its input filename")
        if annotation["review"]["human_reviewed"] or capture["human_reviewed"]:
            raise ValueError("This candidate suite has no completed human review")
        if annotation["review"]["implementation_outputs_seen"] or capture["golden_seen_before_capture"]:
            raise ValueError("Candidate independence declaration is inconsistent")
        claim_ids = [claim["id"] for claim in annotation["claims"]]
        captured_ids = [claim["id"] for claim in capture["claims"]]
        if any(not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", key)
               for key in claim_ids + captured_ids):
            raise ValueError("Claim identities must be portable filename-safe identifiers")
        if (len(set(claim_ids)) != len(claim_ids) or len(set(captured_ids)) != len(captured_ids)
                or set(claim_ids) != set(captured_ids)):
            raise ValueError("Expected and captured claim inventories differ")
        for query in annotation["retrieval_queries"]:
            if not query["query"].strip() or not set(query["expected_claim_ids"]) <= set(claim_ids):
                raise ValueError("Predefined query has no valid target")
        annotations[paper_id], captures[paper_id] = annotation, capture
    return annotations, captures


def compare_reviewed_numbers(annotations, captures, comparison):
    """Use reviewed condition mappings; never align numbers merely by value."""
    from researchvault import evaluation

    results = []
    for row in comparison['records']:
        paper, key = row['paper_id'], row['claim_id']
        golden = next(c for c in annotations[paper]['claims'] if c['id'] == key)
        captured = next(c for c in captures[paper]['claims'] if c['id'] == key)
        names = {n['name']: n for n in captured['numbers']}
        mapped = set()
        for mapping in row['numeric_mappings']:
            index = mapping['golden_index']
            if type(index) is not int or index in mapped or not mapping['mapping_reason'].strip():
                raise ValueError('Numeric mapping must be unique and explain conditions')
            mapped.add(index)
            expected = golden['numeric_facts'][index]
            observed = names[mapping['capture_name']]
            # Units are semantically aligned in the separate review, not silently
            # converted here. The value check retains exact numeric agreement.
            checked = evaluation.numbers([{'claim_id': key + ':' + str(index),
                'unit': expected['unit'], 'required_locations': ['source_annotation', 'capture'],
                'occurrences': [
                    {'location': 'source_annotation', 'value': expected['value'], 'unit': expected['unit']},
                    {'location': 'capture', 'value': observed['value'], 'unit': expected['unit']}]}])
            results.append({'paper_id': paper, 'claim_id': key, 'golden_index': index,
                            'capture_name': mapping['capture_name'], 'passed': checked['passed']})
        if mapped != set(range(len(golden['numeric_facts']))):
            raise ValueError('Every independent numeric expectation needs a reviewed mapping')
    expected_keys = {(p, c['id']) for p, a in annotations.items() for c in a['claims']}
    actual_keys = [(r['paper_id'], r['claim_id']) for r in comparison['records']]
    if len(set(actual_keys)) != len(actual_keys) or set(actual_keys) != expected_keys:
        raise ValueError('Comparison must cover every claim exactly once')
    return {'matched': sum(r['passed'] for r in results), 'total': len(results), 'checks': results,
            'unit_and_condition_review': 'agent reviewed explicit mappings, pending human acceptance'}
