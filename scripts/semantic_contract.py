"""Read-only integrity checks for recorded semantic reviews, never entailment.

The frozen public fixtures are the default inputs. PDFs and original blind
packets are checked only when explicitly supplied; ignored QA storage is never
an implicit dependency. Human-decision records are declarations, not identity
authentication. This module does not invoke the runtime scientific validator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._validation_common import (
    ROOT, COUNTS, PDF_NAMES, ContractError, _inventory, _list, _object,
    _require, _sha, _text, canonical_digest, read_json,
    safe_relative_path as _relative, text_digest, verify_freeze,
)


DIMENSIONS = frozenset({"ENTAILMENT", "SCOPE", "CONDITION", "COMPARATOR",
    "MECHANISM", "CAUSALITY", "QUANTIFICATION", "NEGATIVE_RESULT",
    "LIMITATION", "CONCEPT_BOUNDARY"})
STATUSES = frozenset({"PASS", "FAIL", "UNCERTAIN", "HUMAN_REVIEW_REQUIRED"})
OWNERS = frozenset({"STRUCTURAL_VALIDATOR", "SEMANTIC_EVAL", "HUMAN_REVIEW"})


def _anchor(anchor, paper, location):
    _object(anchor, location)
    _require(anchor.get("pdf_sha256") == paper["pdf_sha256"], "ANCHOR_DIGEST", location,
             "Evidence anchor must identify the frozen PDF")
    page = anchor.get("pdf_page")
    _require(type(page) is int and 1 <= page <= paper["pdf_pages"], "PAGE_BOUNDS",
             location, "Evidence anchor must be within one-based PDF page bounds")
    _text(anchor.get("locator"), location + ".locator")


def _reviewer(document):
    _require(document.get("review_kind") == "agent_review", "REVIEW_KIND", "review",
             "These captured reviews must remain identified as agent reviews")
    reviewer = _object(document.get("reviewer"), "reviewer")
    _text(reviewer.get("model"), "reviewer.model")
    _text(reviewer.get("reasoning_effort"), "reviewer.reasoning_effort")
    for name, expected in (("independent_context", True), ("prior_verdict_seen", False),
                           ("generation_reasoning_seen", False)):
        _require(reviewer.get(name) is expected, "INDEPENDENCE_DISCLOSURE", "reviewer." + name,
                 "Independent blind review must explicitly disclose its context boundaries")


def _human_status(document, target_ids, decisions):
    status = document.get("human_review_status")
    _require(document.get("human_reviewed", False) is not True or status == "reviewed",
             "HUMAN_STATUS", "review", "Human approval cannot be claimed while pending")
    if status == "pending":
        return
    _require(status == "reviewed" and decisions is not None, "HUMAN_STATUS", "review",
             "An agent cannot claim completed human review without an explicit decision record")
    _require(decisions.get("review_kind") == "human_review", "HUMAN_DECISION", "decisions",
             "Decision record must explicitly identify human review")
    _text(_object(decisions.get("reviewer"), "decisions.reviewer").get("identity"),
          "decisions.reviewer.identity")
    rows = _inventory(decisions.get("decisions"), "case_id", "decisions")
    _require(set(rows) == set(target_ids), "HUMAN_DECISION", "decisions",
             "Human decisions must cover every mapped case exactly once")
    for row in rows.values():
        _require(row.get("decision") in {"ACCEPT_GOLD", "REVISE_GOLD", "REJECT_CASE"},
                 "HUMAN_DECISION", row["case_id"], "Human decision must be explicit")
        _text(row.get("reviewed_on"), row["case_id"] + ".reviewed_on")
        _text(row.get("source_evidence"), row["case_id"] + ".source_evidence")


def _review_rows(document, rubric):
    reviews = _inventory(document.get("reviews"), "case_id", "reviews")
    for case_id, row in reviews.items():
        required = set(rubric["report_contract"]["case_fields"])
        _require(required <= set(row), "REVIEW_FIELDS", case_id,
                 "Review omits a required explanatory field")
        for name in required - {"dimensions", "evidence_anchor"}:
            _text(row.get(name), case_id + "." + name)
        dims = _object(row.get("dimensions"), case_id + ".dimensions")
        _require(set(dims) == DIMENSIONS, "DIMENSION_INVENTORY", case_id,
                 "Every review must preserve all ten rubric dimensions")
        for name, dimension in dims.items():
            _object(dimension, case_id + "." + name)
            _require(set(dimension) == {"status", "applicable", "reason"},
                     "DIMENSION_FIELDS", case_id + "." + name,
                     "A dimension requires status, boolean applicability and reason")
            _require(dimension.get("status") in STATUSES and
                     type(dimension.get("applicable")) is bool, "DIMENSION_STATE",
                     case_id + "." + name, "Invalid rubric status or applicability")
            _text(dimension.get("reason"), case_id + "." + name + ".reason")
            _require(dimension["applicable"] or dimension["status"] == "PASS",
                     "NONAPPLICABLE_STATE", case_id + "." + name,
                     "Nonapplicable dimensions must use PASS with an explanation")
        _require(row.get("verdict") in STATUSES, "VERDICT", case_id, "Unknown recorded verdict")
        states = {d["status"] for d in dims.values() if d["applicable"]}
        _require("FAIL" not in states or row["verdict"] == "FAIL", "VERDICT_AGGREGATION",
                 case_id, "Recorded FAIL dimensions cannot be hidden by an overall PASS")
        _require(not (states & {"UNCERTAIN", "HUMAN_REVIEW_REQUIRED"}) or
                 row["verdict"] != "PASS", "VERDICT_AGGREGATION", case_id,
                 "Recorded uncertainty cannot be promoted to an overall PASS")
        _require("score" not in row, "NUMERICAL_SCORE", case_id,
                 "Semantic judgments are recorded without a numerical score")
    return reviews


def validate_contract(repo_root=ROOT, *, papers_dir=None, captures_path=None,
                      results_path=None, blind_packet_path=None, blind_map_path=None,
                      human_decisions_path=None):
    """Return contract diagnostics; validity does not certify a semantic verdict."""
    report = {"valid": False, "errors": [], "checks": {},
              "semantic_judgment_performed": False}
    try:
        report["checks"]["freeze"] = verify_freeze(repo_root, papers_dir=papers_dir)
        golden = Path(repo_root).resolve() / "validation" / "golden"
        b2 = golden / "b2"
        freeze = read_json(b2 / "freeze.json")
        papers = _inventory(freeze["papers"], "paper_id", "freeze.papers")
        rubric = _object(read_json(b2 / "semantic_rubric.json"), "rubric")
        _require(set(_object(rubric.get("dimensions"), "rubric.dimensions")) == DIMENSIONS
                 and set(_list(rubric.get("statuses"), "rubric.statuses")) == STATUSES,
                 "RUBRIC_INVENTORY", "rubric", "The ten dimensions and four statuses must be retained")
        cases_document = _object(read_json(b2 / "semantic_cases.json"), "cases")
        cases = _inventory(cases_document.get("cases"), "case_id", "cases")
        injections = read_json(golden / "reports" / "observed.json")["injections"]
        expected_ids = {r["paper_id"] + "--" + r["name"] for r in injections if r["category"] == "semantic"}
        _require(set(cases) == expected_ids and len(cases) == 9, "CASE_INVENTORY", "cases",
                 "Semantic case inventory must cover the nine original prose cases")
        for case_id, case in cases.items():
            paper_id = case.get("source_paper")
            _require(paper_id in papers, "PAPER_ID", case_id, "Unknown case source paper")
            _anchor(case.get("evidence_anchor"), papers[paper_id], case_id)
            _require(case.get("human_review_status") == "pending", "HUMAN_STATUS", case_id,
                     "Original semantic cases are pending human review")
            original = read_json(golden / "captures" / (paper_id + ".json"))
            last_claim = original["claims"][-1]
            _require(case.get("source_claim_id") == last_claim["id"],
                     "CLAIM_INVENTORY", case_id, "Case source claim does not exist")
            injection = next(r for r in injections if r["paper_id"] + "--" + r["name"] == case_id)
            _require(case.get("expected_error") == injection["name"] and
                     case.get("current_validator_result") == {"detected": injection["detected"],
                         "diagnostic_codes": injection.get("diagnostic_codes", [])},
                     "CASE_BINDING", case_id, "Case must preserve its original deterministic observation")
            _text(case.get("error_class"), case_id + ".error_class")
            _require(case.get("recommended_owner") in OWNERS, "CASE_FIELDS", case_id,
                     "Recorded owner must use the three declared ownership categories")
            _require(type(case.get("deterministically_checkable")) is bool and
                     type(case.get("semantic_reasoning_required")) is bool,
                     "CASE_FIELDS", case_id, "Case responsibility flags must be booleans")
            _object(case.get("candidate"), case_id + ".candidate")
            for name in ("claim", "scope", "observation"):
                _text(case["candidate"].get(name), case_id + ".candidate." + name)
            # Reproduce only the three frozen harness mutations to protect
            # fixture integrity. These literals are not entailment heuristics:
            # no candidate wording is used to predict a semantic verdict.
            expected_candidate = {"claim": last_claim["statement"], "scope": last_claim["scope"],
                                  "observation": last_claim["statement"]}
            if injection["name"] == "wrong_numeric_observation":
                expected_candidate["observation"] = "The reported success rate is 98765 percent."
            elif injection["name"] == "overbroad_scope":
                expected_candidate["scope"] = "Proves universal success on every robot and task."
            elif injection["name"] == "wrong_table_condition":
                expected_candidate["observation"] = "These measurements are from every physical robot with unseen tasks."
            _require(case["candidate"] == expected_candidate and case["evidence_anchor"] == {
                "pdf_sha256": papers[paper_id]["pdf_sha256"], "pdf_page": last_claim["pdf_page"],
                "locator": last_claim["locator"]}, "CASE_BINDING", case_id,
                "Case candidate and anchor must reproduce the original frozen injection fixture")
        capture_path = Path(captures_path) if captures_path else b2 / "semantic_captures.json"
        result_path = Path(results_path) if results_path else b2 / "semantic_results.json"
        capture = _object(read_json(capture_path), "capture")
        result = _object(read_json(result_path), "results")
        _reviewer(capture)
        _reviewer(result)
        _require(result["reviewer"] == capture["reviewer"], "CAPTURE_CHANGED", "reviewer",
                 "Mapping must preserve the captured reviewer disclosure")
        _require(capture.get("rubric_digest") == text_digest(b2 / "semantic_rubric.json"),
                 "RUBRIC_DIGEST", "capture", "Captured review uses a stale rubric")
        _sha(capture.get("blind_packet_digest"), "capture.blind_packet_digest")
        _require(result.get("captures_digest") == text_digest(capture_path),
                 "CAPTURE_DIGEST", "results", "Mapping must identify unchanged captured review bytes")
        for name in ("rubric_digest", "blind_packet_digest"):
            _require(result.get(name) == capture.get(name), "CAPTURE_CHANGED", "results." + name,
                     "Mapping must preserve captured source digests")
        if "cases_digest" in result:
            _require(result["cases_digest"] == text_digest(b2 / "semantic_cases.json"),
                     "CASE_DIGEST", "results", "Mapped case fixture digest is stale")
        mapping = _object(result.get("blind_map"), "results.blind_map")
        reviews = _review_rows(capture, rubric)
        _require(set(mapping) == set(reviews) and set(mapping.values()) == set(cases)
                 and len(set(mapping.values())) == len(mapping), "BLIND_MAP", "results.blind_map",
                 "Blind mapping must be bijective and cover every captured and original case")
        reconstructed_packet = {"cases": [{"case_id": blind_id,
            "source_paper": cases[target]["source_paper"],
            "evidence_anchor": cases[target]["evidence_anchor"],
            "candidate": cases[target]["candidate"]} for blind_id, target in mapping.items()]}
        packet_bytes = (json.dumps(reconstructed_packet, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        _require(hashlib.sha256(packet_bytes).hexdigest() == capture["blind_packet_digest"],
                 "BLIND_PACKET_DIGEST", "capture", "Reconstructed public blind packet differs from its captured digest")
        if blind_map_path is not None:
            _require(mapping == read_json(blind_map_path), "BLIND_MAP", "results.blind_map",
                     "Recorded mapping differs from the explicitly supplied blind map")
        packet = None
        if blind_packet_path is not None:
            _require(capture["blind_packet_digest"] == text_digest(blind_packet_path),
                     "BLIND_PACKET_DIGEST", "capture", "Original blind packet changed")
            packet = _inventory(read_json(blind_packet_path).get("cases"), "case_id", "blind_packet")
            _require(set(packet) == set(reviews), "BLIND_MAP", "blind_packet",
                     "Blind packet and captured case inventories differ")
        mapped = _inventory(result.get("results"), "case_id", "results")
        _require(set(mapped) == set(cases), "CASE_INVENTORY", "results",
                 "Mapped results must cover each original case exactly once")
        for blind_id, target in mapping.items():
            row, case = reviews[blind_id], cases[target]
            _anchor(row.get("evidence_anchor"), papers[case["source_paper"]], blind_id)
            expected_claim = "statement: " + case["candidate"]["claim"] + "\nscope: " + \
                case["candidate"]["scope"] + "\nobservation: " + case["candidate"]["observation"]
            _require(row["claim"] == expected_claim and row["evidence_anchor"] == case["evidence_anchor"],
                     "CANDIDATE_CHANGED", blind_id, "Captured candidate or anchor differs from its case fixture")
            if packet is not None:
                _require(packet[blind_id].get("candidate") == case["candidate"] and
                         packet[blind_id].get("source_paper") == case["source_paper"] and
                         packet[blind_id].get("evidence_anchor") == case["evidence_anchor"],
                         "CANDIDATE_CHANGED", blind_id, "Blind packet differs from the mapped case fixture")
            expected = dict(row, case_id=target, blind_case_id=blind_id)
            _require(mapped[target] == expected, "CAPTURE_CHANGED", target,
                     "Mapped review must preserve all captured values except the disclosed case-ID mapping")
        decisions = _object(read_json(human_decisions_path), "decisions") if human_decisions_path else None
        if decisions is not None:
            _require(decisions.get("captures_digest") == text_digest(capture_path),
                     "HUMAN_DECISION", "decisions", "Human decisions must bind the actual capture")
        _human_status(capture, cases, decisions)
        _human_status(result, cases, decisions)
        report["checks"].update({"recorded_reviews": len(reviews), "mapped_cases": len(mapped),
            "blind_packet_checked": packet is not None, "human_decision_record_checked": decisions is not None})
        report["valid"] = True
    except ContractError as exc:
        report["errors"].append({"code": exc.code, "location": exc.location, "message": exc.message})
    except (KeyError, TypeError, ValueError) as exc:
        report["errors"].append({"code": "MALFORMED_CONTRACT", "location": "contract",
                                 "message": "Required contract fields or types are malformed"})
    return report


def verify_sac_revision(repo_root=ROOT):
    """Bind the recorded agent review to the current proposed SAC statement."""
    verify_freeze(repo_root)
    golden = Path(repo_root).resolve() / "validation" / "golden"
    b2 = golden / "b2"
    revision = _object(read_json(b2 / "sac_revision.json"), "sac_revision")
    review = _object(read_json(b2 / "sac_revision_review.json"), "sac_revision_review")
    capture_path = golden / "captures" / "sac2018.json"
    _require(revision.get("original_capture_digest") == text_digest(capture_path),
             "SAC_CAPTURE_DIGEST", "sac_revision", "Revision must identify the frozen original capture")
    claims = _inventory(read_json(capture_path).get("claims"), "id", "sac_capture")
    claim_id = revision.get("original_claim_id")
    _require(claim_id in claims, "CLAIM_INVENTORY", "sac_revision", "Original revision claim must exist")
    statement = revision.get("revised_statement")
    _text(statement, "sac_revision.revised_statement")
    _require(statement.startswith(claims[claim_id]["statement"]), "SAC_ORIGINAL_CHANGED",
             "sac_revision", "Proposed statement must retain the complete original statement as its prefix")
    _require(revision.get("numbers_unchanged") is True and
             revision.get("review_kind") == "agent_review" and
             revision.get("human_review_status") == "pending", "SAC_REVISION_STATE",
             "sac_revision", "Revision preserves original numbers and remains pending agent review")
    _human_status(revision, {revision.get("case_id")}, None)
    paper = next(row for row in read_json(b2 / "freeze.json")["papers"] if row["paper_id"] == "sac2018")
    _anchor(revision.get("evidence_anchor"), paper, "sac_revision.evidence_anchor")
    _require(revision["evidence_anchor"]["pdf_page"] == claims[claim_id]["pdf_page"],
             "PAGE_BOUNDS", "sac_revision", "Revision anchor must retain the original source page")
    _reviewer(review)
    _require(review.get("human_review_status") == "pending", "HUMAN_STATUS", "sac_revision_review",
             "The proposed revision has no completed human review")
    _human_status(review, {revision.get("case_id")}, None)
    _require(review.get("rubric_digest") == text_digest(b2 / "semantic_rubric.json"),
             "RUBRIC_DIGEST", "sac_revision_review", "Revision review uses a stale rubric")
    rubric = _object(read_json(b2 / "semantic_rubric.json"), "rubric")
    rows = _review_rows(review, rubric)
    _text(revision.get("case_id"), "sac_revision.case_id")
    _require(set(rows) == {revision["case_id"]}, "CASE_INVENTORY", "sac_revision_review",
             "Exactly one review must identify the proposed revision case")
    row = rows[revision["case_id"]]
    _require(row["claim"] == statement, "SAC_REVIEW_STALE", "sac_revision_review",
             "Recorded review must preserve the exact current proposed statement")
    _anchor(row["evidence_anchor"], paper, "sac_revision_review.evidence_anchor")
    _require(row["evidence_anchor"]["pdf_page"] == revision["evidence_anchor"]["pdf_page"],
             "PAGE_BOUNDS", "sac_revision_review", "Revision and review must anchor the same source page")
    return {"valid": True, "case_id": revision["case_id"], "recorded_verdict": row["verdict"],
            "human_review_status": "pending", "semantic_judgment_performed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--papers-dir", type=Path)
    parser.add_argument("--captures", type=Path)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--blind-packet", type=Path)
    parser.add_argument("--blind-map", type=Path)
    parser.add_argument("--human-decisions", type=Path)
    parser.add_argument("--sac-revision", action="store_true")
    args = parser.parse_args(argv)
    report = validate_contract(args.repo_root, papers_dir=args.papers_dir,
        captures_path=args.captures, results_path=args.results,
        blind_packet_path=args.blind_packet, blind_map_path=args.blind_map,
        human_decisions_path=args.human_decisions)
    if args.sac_revision and report["valid"]:
        try:
            report["checks"]["sac_revision"] = verify_sac_revision(args.repo_root)
        except ContractError as exc:
            report["valid"] = False
            report["errors"].append({"code": exc.code, "location": exc.location, "message": exc.message})
        except (KeyError, TypeError, ValueError):
            report["valid"] = False
            report["errors"].append({"code": "MALFORMED_SAC_REVISION", "location": "sac_revision",
                                     "message": "Revision contract fields or types are malformed"})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
