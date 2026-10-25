"""Small, deterministic checks over explicitly captured synthetic outputs.

This module does not generate captures, call a model, infer facts from prose, or
certify research quality. Golden labels calibrate the checker; disagreement asks
for human review and never rewrites either source evidence or golden labels.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PureWindowsPath

from .provenance import digest


PROVENANCE = {"kind": "agent-curated synthetic", "synthetic": True,
              "human_reviewed": False, "real_papers": False}
_OPERATORS = {"grounded_claims", "equals", "subset", "mapped_numbers"}
_CORE = {"fabrication": "grounded_claims", "source_identity": "equals",
         "evidence_ceiling": "subset"}
_MISSING = object()


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read(path):
    raw = Path(path).read_bytes()
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                       parse_constant=lambda value: (_ for _ in ()).throw(
                           ValueError(f"nonfinite JSON value: {value}")))
    digest(value)  # Validate finite JSON before any result is produced.
    return value, hashlib.sha256(raw).hexdigest()


def _local(root, value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("evaluation references must be portable relative paths")
    path = Path(value)
    if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts:
        raise ValueError("evaluation reference must stay in the suite directory")
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("evaluation reference escapes through a symlink")
    return target


def _synthetic(value, label):
    if not isinstance(value, dict) or value != PROVENANCE:
        raise ValueError(f"{label}: phase one accepts agent-curated synthetic inputs only; "
                         "human-reviewed real benchmarks require a later stage")


def _identifier(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _field(value, path):
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _same(left, right):
    # Python considers True == 1; scientific JSON assertions must not.
    return digest(left) == digest(right)


def numbers(claims) -> dict:
    """Compare explicit occurrences, without extracting or selecting a winner.

    Accept a list, {"claims": list}, one claim object, or a mapping from stable
    claim IDs to claim objects. Every claim supplies unit, required_locations,
    occurrences and optional nonnegative absolute tolerance (default zero).
    """
    if isinstance(claims, dict):
        if "claims" in claims:
            claims = claims["claims"]
        elif "claim_id" in claims:
            claims = [claims]
        else:
            claims = [dict(value, claim_id=key) if isinstance(value, dict) else value
                      for key, value in claims.items()]
    if not isinstance(claims, list):
        raise ValueError("numeric claims must be a list or explicit claim mapping")
    digest(claims)
    results, seen = [], set()
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("each numeric claim must be an object")
        claim_id = _identifier(claim.get("claim_id"), "claim_id")
        if claim_id in seen:
            raise ValueError(f"duplicate numeric claim: {claim_id}")
        seen.add(claim_id)
        unit = _identifier(claim.get("unit"), "unit")
        locations = claim.get("required_locations")
        if (not isinstance(locations, list) or len(locations) < 2 or
                any(not isinstance(item, str) or not item.strip() for item in locations)
                or len(set(locations)) != len(locations)):
            raise ValueError("required_locations needs at least two distinct location names")
        tolerance = claim.get("tolerance", 0)
        if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
                or not math.isfinite(tolerance) or tolerance < 0):
            raise ValueError("tolerance must be a finite nonnegative number")
        occurrences = claim.get("occurrences")
        if not isinstance(occurrences, list):
            raise ValueError("occurrences must be a list")
        reasons, found, values = [], set(), []
        for occurrence in occurrences:
            if not isinstance(occurrence, dict):
                reasons.append("malformed occurrence")
                continue
            location = occurrence.get("location")
            if not isinstance(location, str) or not location.strip():
                reasons.append("occurrence lacks an explicit location")
                continue
            if location in found:
                reasons.append(f"duplicate location: {location}")
            found.add(location)
            value = occurrence.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                reasons.append(f"non-numeric value at {location}")
            else:
                values.append(value)
            if occurrence.get("unit") != unit:
                reasons.append(f"unit mismatch at {location}; conversion is not implicit")
        missing = sorted(set(locations) - found)
        if missing:
            reasons.append("missing locations: " + ", ".join(missing))
        if len(values) >= 2 and max(values) - min(values) > tolerance:
            reasons.append("mapped values disagree beyond absolute tolerance")
        if len(values) < 2:
            reasons.append("fewer than two numeric occurrences")
        results.append({"claim_id": claim_id,
                        "expected": {"unit": unit, "required_locations": locations,
                                     "absolute_tolerance": tolerance, "agreement": "all occurrences"},
                        "observed": occurrences, "status": "fail" if reasons else "pass",
                        "evidence": {"reasons": reasons, "missing_locations": missing,
                                     "winner_selected": False}})
    passed = all(item["status"] == "pass" for item in results)
    return {"passed": passed, "status": ("not_applicable" if not results else
                                         "pass" if passed else "fail"), "claims": results}


def _grounded(source, output):
    facts, segments = source.get("facts"), source.get("segments")
    if not isinstance(facts, dict) or not isinstance(segments, dict):
        raise ValueError("source must provide facts and locator-keyed segments")
    if any(not isinstance(text, str) for text in segments.values()):
        raise ValueError("source segments must contain text")
    claims, quotes = output.get("claims"), output.get("quotes")
    reasons = []
    if not isinstance(claims, list) or not isinstance(quotes, list):
        reasons.append("capture must explicitly supply claims and quotes lists")
    else:
        seen = set()
        for claim in claims:
            if not isinstance(claim, dict) or not isinstance(claim.get("fact_id"), str):
                reasons.append("claim lacks an explicit fact mapping")
                continue
            key = claim["fact_id"]
            if key in seen or key not in facts or not _same(claim.get("value"), facts[key]):
                reasons.append(f"unsupported or duplicate factual assertion: {key}")
            seen.add(key)
        for quote in quotes:
            if not isinstance(quote, dict):
                reasons.append("malformed quotation")
                continue
            text, locator = quote.get("text"), quote.get("locator")
            if (not isinstance(text, str) or not text or not isinstance(locator, str)
                    or locator not in segments or text not in segments[locator]):
                reasons.append("quotation is absent from its specified source locator")
    return {"facts": facts, "segments": segments}, {"claims": claims, "quotes": quotes}, reasons


def _criterion(rule, source, output):
    operation = rule["operator"]
    if operation == "grounded_claims":
        expected, observed, reasons = _grounded(source, output)
    else:
        observed = _field(output, rule["field"])
        if operation == "mapped_numbers":
            expected = {"agreement": "all explicitly mapped occurrences"}
        else:
            expected = _field(source, rule["expected_field"])
            if expected is _MISSING:
                raise ValueError(f"source is missing expected field for {rule['id']}")
        if observed is _MISSING:
            observed, reasons = None, ["required capture field is missing"]
        elif operation == "equals":
            reasons = [] if _same(expected, observed) else ["observed value differs from source expectation"]
        elif operation == "subset":
            if (not isinstance(expected, list) or not all(isinstance(item, str) for item in expected)):
                raise ValueError("evidence ceiling must be an explicit list of scope labels")
            reasons = ([] if isinstance(observed, list) and all(isinstance(item, str) for item in observed)
                       and set(observed).issubset(expected) else ["claim exceeds or omits its evidence ceiling"])
        else:
            try:
                check = numbers(observed)
                reasons = [item for claim in check["claims"] for item in claim["evidence"]["reasons"]]
            except ValueError as exc:
                reasons = [str(exc)]
    return {"id": rule["id"], "severity": rule["severity"], "expected": expected,
            "observed": observed, "status": "fail" if reasons else "pass",
            "evidence": {"reasons": reasons}}


def run(suite_path, captures_path, output_path=None) -> dict:
    """Evaluate existing captured output with a versioned local rubric."""
    suite_path, captures_path = Path(suite_path), Path(captures_path)
    suite, suite_hash = _read(suite_path)
    captures, captures_hash = _read(captures_path)
    if not isinstance(suite, dict) or not isinstance(captures, dict):
        raise ValueError("suite and captures must be JSON objects")
    _synthetic(suite.get("provenance"), "suite")
    _synthetic(captures.get("provenance"), "captures")
    suite_id = _identifier(suite.get("suite_id"), "suite_id")
    suite_version = _identifier(suite.get("version"), "suite version")
    rubric_path = _local(suite_path.parent, suite.get("rubric"))
    golden_path = _local(suite_path.parent, suite.get("golden"))
    rubric, rubric_hash = _read(rubric_path)
    golden, golden_hash = _read(golden_path)
    if not isinstance(rubric, dict) or not isinstance(golden, dict):
        raise ValueError("rubric and golden must be objects")
    _synthetic(golden.get("provenance"), "golden")
    rubric_version = _identifier(rubric.get("version"), "rubric version")
    rules = rubric.get("criteria")
    if not isinstance(rules, list) or not rules:
        raise ValueError("rubric needs explicit criteria")
    rule_ids = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("rubric criteria must be objects")
        key = _identifier(rule.get("id"), "criterion id")
        if key in rule_ids or rule.get("operator") not in _OPERATORS:
            raise ValueError("duplicate criterion or unknown deterministic operator")
        rule_ids.add(key)
        if rule.get("severity") not in {"critical", "major", "minor"}:
            raise ValueError("criterion severity is required")
        if rule["operator"] != "grounded_claims":
            _identifier(rule.get("field"), "criterion field")
        if rule["operator"] in {"equals", "subset"}:
            _identifier(rule.get("expected_field"), "criterion expected_field")
    for key, operation in _CORE.items():
        rule = next((item for item in rules if item["id"] == key), None)
        if rule is None or rule["operator"] != operation or rule["severity"] != "critical":
            raise ValueError(f"rubric must retain the critical {key} check")
    cases, captured, expected_cases = suite.get("cases"), captures.get("captures"), golden.get("cases")
    if not isinstance(cases, list) or not cases or not isinstance(captured, dict) or not isinstance(expected_cases, dict):
        raise ValueError("suite cases must be a nonempty list; captures/golden cases must be mappings")
    case_ids = [_identifier(case.get("id"), "case id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(cases) or len(set(case_ids)) != len(cases):
        raise ValueError("case IDs must be distinct objects with explicit IDs")
    if set(expected_cases) != set(case_ids) or not set(captured).issubset(case_ids):
        raise ValueError("golden IDs must match the suite; unknown capture IDs are rejected")
    report_cases, review = [], []
    input_paths = {suite_path.resolve(), captures_path.resolve(), rubric_path, golden_path}
    for case in cases:
        key = case["id"]
        source_path = _local(suite_path.parent, case.get("source"))
        input_paths.add(source_path)
        source, source_hash = _read(source_path)
        if not isinstance(source, dict):
            raise ValueError("case source must be an object")
        _synthetic(source.get("provenance"), f"source {key}")
        expected = expected_cases[key]
        all_ids = rule_ids | {"source_digest"}
        if not isinstance(expected, dict) or set(expected) != all_ids or any(value not in {"pass", "fail", "missing"} for value in expected.values()):
            raise ValueError(f"golden {key} must label every criterion exactly once")
        capture = captured.get(key)
        if capture is None:
            criteria = [{"id": rule["id"], "severity": rule["severity"],
                         "expected": "captured output", "observed": None, "status": "missing",
                         "evidence": {"reasons": ["capture is missing"]}} for rule in rules]
            criteria.append({"id": "source_digest", "severity": "critical", "expected": source_hash,
                             "observed": None, "status": "missing", "evidence": {"reasons": ["capture is missing"]}})
            capture_hash = None
        else:
            if not isinstance(capture, dict) or not isinstance(capture.get("output"), dict):
                raise ValueError(f"capture {key} must contain a structured output object")
            capture_hash = digest(capture)
            criteria = [_criterion(rule, source, capture["output"]) for rule in rules]
            source_matches = capture.get("source_digest") == source_hash
            criteria.append({"id": "source_digest", "severity": "critical", "expected": source_hash,
                             "observed": capture.get("source_digest"), "status": "pass" if source_matches else "fail",
                             "evidence": {"reasons": [] if source_matches else ["capture source digest is missing or stale"]}})
        for criterion in criteria:
            criterion["evidence"].update({"source": case["source"], "source_digest": source_hash,
                                         "capture_hash": capture_hash})
            criterion["golden_status"] = expected[criterion["id"]]
            criterion["golden_agreement"] = criterion["status"] == criterion["golden_status"]
            if not criterion["golden_agreement"]:
                review.append({"case_id": key, "criterion_id": criterion["id"],
                               "expected": criterion["golden_status"], "observed": criterion["status"],
                               "action": "human-review-required; preserve source and golden unchanged"})
        status = "missing" if capture is None else ("pass" if all(item["status"] == "pass" for item in criteria) else "fail")
        report_cases.append({"id": key, "status": status, "source_digest": source_hash,
                             "capture_hash": capture_hash, "case_definition_digest": digest(case),
                             "golden_digest": digest(expected), "criteria": criteria,
                             "critical_failure": any(item["severity"] == "critical" and item["status"] != "pass" for item in criteria)})
    summary = {name: sum(case["status"] == name for case in report_cases) for name in ("pass", "fail", "missing")}
    summary["critical_failures"] = sum(case["critical_failure"] for case in report_cases)
    result = {"evaluation_format": 1, "suite_id": suite_id, "suite_version": suite_version,
              "provenance": dict(PROVENANCE), "rubric_version": rubric_version,
              "suite_digest": suite_hash, "rubric_digest": rubric_hash, "golden_digest": golden_hash,
              "captures_digest": captures_hash, "run_id": captures.get("run_id"),
              "producer_version": captures.get("producer_version"), "cases": report_cases,
              "summary": summary, "passed": summary["fail"] == 0 and summary["missing"] == 0 and not review,
              "golden_agreement": not review, "human_review_required": bool(review),
              "review_requests": review,
              "limitations": "Deterministic assertions on synthetic structured captures; not a real-paper benchmark or semantic truth assessment."}
    if output_path is not None:
        target = Path(output_path)
        if target.resolve() in input_paths:
            raise ValueError("evaluation output cannot overwrite an input or source")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    return result


def compare(left: dict, right: dict) -> dict:
    """Describe compatible changes; changed measuring rules require re-evaluation."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise ValueError("comparison needs two evaluation reports")
    reasons = []
    for field in ("evaluation_format", "suite_id", "suite_version", "provenance", "rubric_version", "rubric_digest"):
        if field not in left or field not in right or left[field] != right[field]:
            reasons.append(f"changed or missing {field}")

    def indexed(report):
        cases = report.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ValueError("comparison report needs case results")
        result = {}
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("id"), str) or case["id"] in result:
                raise ValueError("malformed or duplicate comparison case")
            result[case["id"]] = case
        return result

    a, b = indexed(left), indexed(right)
    for key in sorted(a.keys() & b.keys()):
        for field in ("source_digest", "golden_digest", "case_definition_digest"):
            if not a[key].get(field) or a[key][field] != b[key].get(field):
                reasons.append(f"{key}: changed or missing {field}")
    result = {"comparable": not reasons, "passed": False, "blocked": bool(reasons),
              "reevaluation_required": bool(reasons), "reasons": reasons,
              "regressions": [], "improvements": [], "unchanged": [], "new_failures": [],
              "added_cases": sorted(b.keys() - a.keys()), "removed_cases": sorted(a.keys() - b.keys()),
              "human_review_required": bool(left.get("human_review_required") or right.get("human_review_required"))}
    if reasons:
        return result

    def criteria(case):
        values = case.get("criteria")
        if not isinstance(values, list) or not values:
            raise ValueError("comparison case needs structured criteria")
        result = {}
        for item in values:
            if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                    or item["id"] in result or item.get("status") not in {"pass", "fail", "missing"}):
                raise ValueError("comparison criterion is malformed or duplicated")
            result[item["id"]] = item["status"]
        return result

    for key in sorted(b):
        prior = criteria(a[key]) if key in a else {}
        current = criteria(b[key])
        if key in a and set(prior) != set(current):
            raise ValueError("criterion inventory changed without a rubric change; re-evaluation required")
        for criterion_id, status in current.items():
            before = prior.get(criterion_id)
            item = {"case_id": key, "criterion_id": criterion_id, "before": before, "after": status}
            if before is None:
                if status != "pass":
                    result["new_failures"].append(item)
            elif before == status:
                result["unchanged"].append(item)
            elif before == "pass":
                result["regressions"].append(item)
                result["new_failures"].append(item)
            elif status == "pass":
                result["improvements"].append(item)
            else:
                result["unchanged"].append(item)
    result["passed"] = not (result["regressions"] or result["new_failures"] or
                             result["removed_cases"] or result["human_review_required"])
    return result
