"""Scientific decisions, immutable claim/design content and attempt accounting."""
from __future__ import annotations

import re

from .documents import diagnostic, read_record, scan
from .provenance import canonical, create_receipt, digest, history, read_receipt

VERDICTS = {"SUPPORTED", "NOT_SUPPORTED", "INCONCLUSIVE", "NOT_TESTED"}
TRIAL_STATES = {"completed", "failed", "aborted", "excluded"}
IDENTIFIERS = {"research-question": "question_id", "research-gap": "gap_id",
               "research-hypothesis": "hypothesis_id", "research-idea": "idea_id",
               "research-card": "card_id", "experiment-contract": "experiment_id",
               "experiment-trial": "trial_id", "result-bundle": "result_id",
               "claim-ledger": "claim_id", "research-project": "project_id"}
CLAIM_FIELDS = ("card_id", "claim_id", "proposition", "scope", "comparisons", "mechanism",
                "falsifiers", "evidence_obligations")
DESIGN_FIELDS = ("experiment_id", "card_id", "claim_id", "claim_digest", "conditions",
                 "baselines", "metrics", "denominator", "exclusions", "abort_policy",
                 "seeds", "analysis_plan")
CEILINGS = {"setting", "robot", "morphology", "task", "environment", "seeds",
            "replication", "ood", "transfer"}


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _list(value, name, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{name} must be {'a nonempty' if nonempty else 'a'} list")
    return value


def _mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _strings(value, name, nonempty=False):
    items = _list(value, name, nonempty)
    for item in items:
        _text(item, name)
    if len(set(items)) != len(items):
        raise ValueError(f"{name} contains duplicates")
    return items


def lock_content(data, kind):
    """The semantic fields frozen by each specialized scientific receipt."""
    if kind not in {"claim", "design"}:
        raise ValueError("lock kind must be claim or design")
    required_type = "research-card" if kind == "claim" else "experiment-contract"
    if data.get("type") != required_type:
        raise ValueError(f"{kind} lock requires {required_type}")
    fields = CLAIM_FIELDS if kind == "claim" else DESIGN_FIELDS
    missing = [field for field in fields if field not in data]
    if missing:
        raise ValueError("lock fields missing: " + ", ".join(missing))
    for field in ("card_id", "claim_id") + (("experiment_id", "claim_digest") if kind == "design" else ()):
        _text(data[field], field)
    if kind == "claim":
        for field in ("proposition", "mechanism"):
            _text(data[field], field)
        for field in ("scope", "comparisons", "falsifiers", "evidence_obligations"):
            if not isinstance(data[field], (dict, list)) or not data[field]:
                raise ValueError(f"{field} must contain an explicit scientific definition")
    else:
        _strings(data["conditions"], "conditions", True)
        _list(data["baselines"], "baselines", True)
        _list(data["metrics"], "metrics", True)
        seeds = _list(data["seeds"], "seeds", True)
        if any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds) or len(set(seeds)) != len(seeds):
            raise ValueError("seeds must be distinct integers")
        denominator = _mapping(data["denominator"], "denominator")
        _text(denominator.get("unit"), "denominator.unit")
        statuses = _strings(denominator.get("include_statuses"), "denominator.include_statuses", True)
        if not set(statuses) <= TRIAL_STATES:
            raise ValueError("unknown denominator status")
        for rule in _list(data["exclusions"], "exclusions"):
            _text(_mapping(rule, "exclusion").get("reason"), "exclusion.reason")
        abort = _mapping(data["abort_policy"], "abort_policy")
        _strings(abort.get("allowed_reasons"), "abort_policy.allowed_reasons")
        if not isinstance(abort.get("include_in_denominator"), bool):
            raise ValueError("abort_policy.include_in_denominator must be boolean")
        if abort["include_in_denominator"] != ("aborted" in statuses):
            raise ValueError("abort policy disagrees with denominator statuses")
        if not isinstance(data["analysis_plan"], (str, dict)) or not data["analysis_plan"]:
            raise ValueError("analysis_plan must be explicit")
    content = {field: data[field] for field in fields}
    canonical(content)
    return content


def _receipt_for(settings, kind, object_id, fingerprint):
    _text(fingerprint, kind + "_digest")
    candidates = history(settings, kind, object_id)
    found = next((item for item in candidates if item["snapshot_digest"] == fingerprint), None)
    if found is None:
        raise ValueError(f"{kind} digest has no receipt for {object_id}")
    return found


def freeze(settings, path, kind, apply=False, previous=None, reason=None, timing="pre-result"):
    record = read_record(settings.resolve(str(path)), settings.vault)
    content = lock_content(record.data, kind)
    if timing not in {"pre-result", "post-result"}:
        raise ValueError("scientific lock timing must be pre-result or post-result")
    records = scan(settings)
    object_id = content["card_id" if kind == "claim" else "experiment_id"]
    if kind == "claim":
        receipts = history(settings, kind, object_id)
        if any(item["snapshot"].get("claim_id") != content["claim_id"] for item in receipts):
            raise ValueError("claim_id must remain stable across revisions of the same card")
    if kind == "design":
        claim = _receipt_for(settings, "claim", content["card_id"], content["claim_digest"])
        if claim["snapshot"]["claim_id"] != content["claim_id"]:
            raise ValueError("design claim identity differs from frozen claim")
        if claim["timing"] == "post-result" and timing != "post-result":
            raise ValueError("a post-result claim requires an exploratory design")
    results_exist = any(item.data.get("type") == "result-bundle" and
                        (item.data.get("claim_id") == content["claim_id"] if kind == "claim"
                         else item.data.get("experiment_id") == object_id) for item in records)
    if results_exist and timing != "post-result":
        raise ValueError("results already exist; this lock must be post-result and exploratory")
    result = create_receipt(settings, kind=kind, object_id=object_id, source=record.relative,
                            content=content, apply=apply, previous=previous,
                            reason=reason, timing=timing)
    result["metadata"] = {kind + "_digest": result["digest"],
                          kind + "_receipt": result["receipt"],
                          kind + "_lock_status": "exploratory" if result["envelope"]["timing"] == "post-result" else "locked"}
    return result


def _artifact_paths(settings, values, field, nonempty=False):
    for path in _strings(values, field, nonempty):
        if not settings.resolve(path).is_file():
            raise ValueError(f"{field} artifact unavailable: {path}")


def _ceiling(value):
    value = _mapping(value, "evidence_ceiling")
    if set(value) != CEILINGS:
        raise ValueError("evidence_ceiling must explicitly cover " + ", ".join(sorted(CEILINGS)))
    for key, bound in value.items():
        if not isinstance(bound, list):
            raise ValueError(f"evidence_ceiling.{key} must be a list of evidenced values")
        canonical(bound)
    return value


def check(settings, records):
    """Read-only structural checks; never infer a verdict from observations."""
    issues = []
    indexes = {kind: {} for kind in IDENTIFIERS}
    for record in records:
        data = record.data
        kind = data.get("type")
        if not isinstance(kind, str) or kind not in IDENTIFIERS:
            continue
        try:
            identifier = _text(data.get(IDENTIFIERS[kind]), IDENTIFIERS[kind])
            if identifier in indexes[kind]:
                raise ValueError(f"duplicate {kind} identity: {identifier}")
            indexes[kind][identifier] = record
        except ValueError as exc:
            issues.append(diagnostic("science.identity", record.relative, str(exc)))

    def report(code, record, detail, level="error"):
        issues.append(diagnostic(code, record.relative, detail, level))

    def design_for(data):
        contract = indexes["experiment-contract"].get(data.get("experiment_id"))
        if contract is None:
            raise ValueError("experiment_id does not resolve to a contract")
        receipt = _receipt_for(settings, "design", data["experiment_id"], data.get("design_digest"))
        return receipt

    for record in records:
        data = record.data
        kind = data.get("type")
        try:
            if kind in {"research-card", "experiment-contract"}:
                lock = "claim" if kind == "research-card" else "design"
                object_id = _text(data.get("card_id" if lock == "claim" else "experiment_id"), "object identity")
                receipts = history(settings, lock, object_id)
                if lock == "claim" and any(item["snapshot"].get("claim_id") != data.get("claim_id") for item in receipts):
                    raise ValueError("claim_id must remain stable across revisions of the same card")
                fingerprint, reference = data.get(lock + "_digest"), data.get(lock + "_receipt")
                if not fingerprint and not reference:
                    if receipts:
                        report("science.lock-reference", record, "receipt history exists but page lock metadata was removed")
                    continue
                content = lock_content(data, lock)
                receipt = _receipt_for(settings, lock, object_id, fingerprint)
                pointed = read_receipt(settings, reference)
                if pointed != receipt or digest(content) != fingerprint:
                    raise ValueError("current scientific definition differs from its lock")
                if receipt != receipts[-1]:
                    raise ValueError("page references an old lock instead of the latest revision")
                status = "exploratory" if receipt["timing"] == "post-result" else "locked"
                if data.get(lock + "_lock_status") != status:
                    raise ValueError("lock status disagrees with immutable receipt timing")
                if lock == "design":
                    claim = _receipt_for(settings, "claim", content["card_id"], content["claim_digest"])
                    if content["claim_id"] != claim["snapshot"]["claim_id"]:
                        raise ValueError("design refers to a different claim")
            elif kind == "experiment-trial":
                receipt = design_for(data)
                design = receipt["snapshot"]
                if data.get("condition") not in design["conditions"]:
                    raise ValueError("trial condition was not declared in the frozen design")
                if isinstance(data.get("seed"), bool) or data.get("seed") not in design["seeds"]:
                    raise ValueError("trial seed was not declared in the frozen design")
                for field in ("robot", "environment"):
                    _text(data.get(field), field)
                if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", str(data.get("git_commit", ""))):
                    raise ValueError("trial requires an exact Git commit, not a branch or abbreviation")
                config = _mapping(data.get("config"), "config")
                if not config:
                    raise ValueError("trial config must record effective parameters")
                canonical(config)
                state = data.get("status")
                if state not in TRIAL_STATES:
                    raise ValueError("unknown trial status")
                included = data.get("included_in_denominator")
                if not isinstance(included, bool):
                    raise ValueError("included_in_denominator must be boolean")
                expected = state in design["denominator"]["include_statuses"]
                if state == "aborted":
                    if data.get("abort_reason") not in design["abort_policy"]["allowed_reasons"]:
                        raise ValueError("abort reason is not covered by the frozen abort policy")
                    expected = design["abort_policy"]["include_in_denominator"]
                if state == "excluded":
                    if data.get("exclusion_reason") not in [rule["reason"] for rule in design["exclusions"]]:
                        raise ValueError("trial exclusion was not predeclared")
                if included != expected:
                    raise ValueError("trial denominator decision contradicts frozen policy")
                _artifact_paths(settings, data.get("raw_artifacts"), "raw_artifacts")
                if not data["raw_artifacts"]:
                    if state == "completed":
                        raise ValueError("completed trial has no raw artifact")
                    _text(data.get("missingness_reason"), "missingness_reason")
                retry_id = data.get("retry_of")
                if retry_id:
                    prior = indexes["experiment-trial"].get(retry_id)
                    if prior is None or retry_id == data.get("trial_id"):
                        raise ValueError("retry must retain and reference a different prior trial")
                    for field in ("experiment_id", "design_digest", "condition"):
                        if prior.data.get(field) != data.get(field):
                            raise ValueError("retry must preserve experiment, design and condition lineage")
                    visited = {data.get("trial_id")}
                    while prior is not None:
                        if prior.data["trial_id"] in visited:
                            raise ValueError("retry lineage is cyclic")
                        visited.add(prior.data["trial_id"])
                        prior = indexes["experiment-trial"].get(prior.data.get("retry_of"))
            elif kind == "result-bundle":
                receipt = design_for(data)
                design = receipt["snapshot"]
                if data.get("claim_id") != design["claim_id"] or data.get("claim_digest") != design["claim_digest"]:
                    raise ValueError("result must preserve the claim originally paired with its design")
                verdict = data.get("verdict")
                if verdict not in VERDICTS:
                    raise ValueError("result verdict is not an experimental judgment")
                trial_ids = set(_strings(data.get("trial_ids"), "trial_ids"))
                relevant = {identifier for identifier, trial in indexes["experiment-trial"].items()
                            if trial.data.get("experiment_id") == data["experiment_id"]
                            and trial.data.get("design_digest") == data["design_digest"]}
                if trial_ids != relevant:
                    raise ValueError(f"result must account for every attempt; missing={sorted(relevant-trial_ids)}, unknown={sorted(trial_ids-relevant)}")
                trials = [indexes["experiment-trial"][identifier].data for identifier in trial_ids]
                missingness = _list(data.get("missingness", []), "missingness")
                missing_ids = set()
                for item in missingness:
                    item = _mapping(item, "missingness entry")
                    _text(item.get("reason"), "missingness.reason")
                    missing_ids.add(_text(item.get("trial_id"), "missingness.trial_id"))
                actual_missing = {trial["trial_id"] for trial in trials if not trial.get("raw_artifacts")}
                if missing_ids != actual_missing:
                    raise ValueError("result missingness must disclose exactly the attempts without raw artifacts")
                completed = [trial for trial in trials if trial.get("status") == "completed"
                             and trial.get("included_in_denominator") is True]
                if verdict == "NOT_TESTED" and completed:
                    raise ValueError("NOT_TESTED conflicts with completed included trials")
                if verdict in {"SUPPORTED", "NOT_SUPPORTED"} and (not completed or actual_missing):
                    raise ValueError("a definitive verdict needs completed evidence and no unresolved raw missingness")
                if data.get("status") == "completed":
                    _artifact_paths(settings, data.get("analysis_artifacts"), "analysis_artifacts", True)
                    _ceiling(data.get("evidence_ceiling"))
                    if receipt["timing"] == "post-result" and data.get("analysis_status") != "exploratory":
                        raise ValueError("post-result design cannot be reported as confirmatory")
                elif data.get("status") != "draft":
                    raise ValueError("result status must be draft or completed")
            elif kind == "claim-ledger":
                verdict = data.get("verdict")
                if verdict not in VERDICTS:
                    raise ValueError("ledger verdict is not an experimental judgment")
                result_ids = _strings(data.get("result_ids"), "result_ids")
                literature = _list(data.get("literature", []), "literature")
                if not result_ids and not literature:
                    raise ValueError("claim ledger needs explicit result or literature evidence")
                ceiling = _ceiling(data.get("evidence_ceiling"))
                bound_results = []
                for identifier in result_ids:
                    result = indexes["result-bundle"].get(identifier)
                    if result is None or result.data.get("claim_id") != data.get("claim_id"):
                        raise ValueError("ledger result must resolve to the same claim")
                    bound_results.append(result.data)
                if verdict != "NOT_TESTED" and not bound_results:
                    raise ValueError("literature cannot establish an experimental verdict")
                if verdict in {"SUPPORTED", "NOT_SUPPORTED"} and any(result.get("status") != "completed" for result in bound_results):
                    raise ValueError("a definitive ledger requires completed result evidence, not draft results")
                if verdict in {"SUPPORTED", "NOT_SUPPORTED"} and any(result.get("verdict") != verdict for result in bound_results):
                    raise ValueError("ledger cannot relabel inconclusive or conflicting results as definitive")
                for result in bound_results:
                    result_ceiling = _ceiling(result.get("evidence_ceiling"))
                    for dimension in CEILINGS:
                        if not {digest(value) for value in ceiling[dimension]} <= {digest(value) for value in result_ceiling[dimension]}:
                            raise ValueError(f"ledger exceeds result evidence ceiling for {dimension}")
                for link in literature:
                    _text(link, "literature reference")
                    linked = next((item for item in records if item.relative == link), None)
                    if linked is None or linked.data.get("type") != "literature-note":
                        raise ValueError("ledger literature must resolve to an actual Paper Note")
            elif kind == "research-idea" and data.get("status") not in {None, "proposed", "abandoned", "merged", "narrowed", "more-literature", "active"}:
                raise ValueError("unknown idea disposition")
        except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
            report("science." + (kind if isinstance(kind, str) else "malformed"), record, str(exc))
    return issues
