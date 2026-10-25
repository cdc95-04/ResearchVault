"""Bounded systematic review records and frozen, revisable corpus evidence."""
from __future__ import annotations

from datetime import date, datetime

from .documents import diagnostic, load_yaml, read_record
from .identity import KEY, arxiv, doi
from .provenance import canonical, create_receipt, digest, history, read_receipt

CHALLENGES = {"supporting", "competing", "contradictory", "null", "alternative-mechanism"}
PROTOCOL_FIELDS = ("review_id", "version", "scope", "inclusion_criteria", "exclusion_criteria",
                   "query_families", "sources", "seed_papers", "citation_policy")


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _list(value, name):
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _strings(value, name):
    values = _list(value, name)
    for item in values:
        _text(item, name)
    if len(set(values)) != len(values):
        raise ValueError(f"{name} contains duplicates")
    return values


def _date(value, name):
    if isinstance(value, (date, datetime)):
        return
    try:
        datetime.fromisoformat(_text(value, name).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must record an actual ISO execution date/time") from exc


def _paper_id(value):
    value = _text(value, "paper_id")
    prefix, _, identifier = value.partition(":")
    if prefix in {"doi", "arxiv"}:
        normalized = doi(identifier) if prefix == "doi" else arxiv(identifier)
        if normalized and identifier == normalized:
            return value
        raise ValueError("paper_id must use a canonical DOI or arXiv identifier")
    parts = value.split(":")
    if len(parts) == 4 and parts[0] == "zotero" and KEY.fullmatch(parts[3]):
        if parts[1:3] == ["user", "local"]:
            return value
        if parts[1] == "group" and parts[2].isascii() and parts[2].isdigit() and int(parts[2]) > 0 and str(int(parts[2])) == parts[2]:
            return value
    raise ValueError("paper_id must carry a canonical DOI, arXiv or namespaced Zotero parent identity")


def protocol_content(data):
    if data.get("type") != "review-protocol":
        raise ValueError("Corpus Freeze requires a review-protocol")
    missing = [key for key in PROTOCOL_FIELDS if key not in data]
    if missing:
        raise ValueError("protocol fields missing: " + ", ".join(missing))
    _text(data["review_id"], "review_id")
    if isinstance(data["version"], bool) or not isinstance(data["version"], (str, int)) or not str(data["version"]):
        raise ValueError("protocol version must be a nonempty string or integer")
    if not isinstance(data["scope"], (str, dict)) or not data["scope"]:
        raise ValueError("scope must explicitly define the review question")
    for name in ("inclusion_criteria", "exclusion_criteria", "sources"):
        if not _strings(data[name], name):
            raise ValueError(f"{name} must be established before screening")
    for identifier in _strings(data["seed_papers"], "seed_papers"):
        _paper_id(identifier)
    families = _list(data["query_families"], "query_families")
    seen = set()
    for family in families:
        family = _mapping(family, "query family")
        identifier = _text(family.get("family_id"), "family_id")
        if identifier in seen:
            raise ValueError("duplicate query family identity")
        seen.add(identifier)
        _text(family.get("purpose"), "query family purpose")
        if not _strings(family.get("queries"), "query family queries"):
            raise ValueError("query family must define planned queries")
    if not families:
        raise ValueError("protocol needs query families")
    policy = _mapping(data["citation_policy"], "citation_policy")
    rounds = policy.get("max_rounds")
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 0:
        raise ValueError("citation max_rounds must be a nonnegative integer")
    if not set(_strings(policy.get("directions"), "citation directions")) <= {"backward", "forward"}:
        raise ValueError("unknown citation direction")
    content = {key: data[key] for key in PROTOCOL_FIELDS}
    canonical(content)
    return content


def load_corpus(settings, protocol):
    path = settings.resolve(_text(protocol.get("corpus_path"), "corpus_path"))
    corpus = load_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(corpus, dict):
        raise ValueError("corpus YAML must be a mapping")
    return corpus


def corpus_content(protocol, corpus):
    """Validate recorded execution, not a paper-count proxy for completeness."""
    planned = protocol_content(protocol)
    if corpus.get("schema_version") != 2 or corpus.get("review_id") != planned["review_id"]:
        raise ValueError("corpus schema or review identity differs from protocol")
    if corpus.get("protocol_version") != planned["version"]:
        raise ValueError("corpus version differs from protocol")
    families = {family["family_id"]: family for family in planned["query_families"]}
    for search in _list(corpus.get("searches"), "searches"):
        search = _mapping(search, "search")
        family_id = _text(search.get("family_id"), "search.family_id")
        if family_id not in families:
            raise ValueError("executed query family was not defined by protocol")
        if search.get("query") not in families[family_id]["queries"]:
            raise ValueError("executed query differs from prior query definition; revise protocol")
        if search.get("source") not in planned["sources"]:
            raise ValueError("search source was not declared")
        _date(search.get("executed_at"), "search.executed_at")
        _strings(search.get("returned_ids"), "search.returned_ids")
    identities = set()
    for paper in _list(corpus.get("papers"), "papers"):
        paper = _mapping(paper, "paper")
        paper_id = _paper_id(paper.get("paper_id"))
        if paper_id in identities:
            raise ValueError("corpus contains a duplicate canonical paper identity")
        identities.add(paper_id)
        if paper.get("decision") not in {"include", "exclude", "pending"}:
            raise ValueError("screening decision must be include, exclude or pending")
        _text(paper.get("reason"), "screening reason")
    dedup = _mapping(corpus.get("deduplication"), "deduplication")
    if not isinstance(dedup.get("performed"), bool):
        raise ValueError("deduplication.performed must be boolean")
    _text(dedup.get("method"), "deduplication.method")
    for duplicate in _list(dedup.get("duplicates"), "deduplication.duplicates"):
        duplicate = _mapping(duplicate, "duplicate decision")
        if duplicate.get("kept") not in identities or duplicate.get("removed") == duplicate.get("kept"):
            raise ValueError("dedup decision needs a retained identity and a distinct removed candidate")
        _text(duplicate.get("removed"), "duplicate removed candidate")
        _text(duplicate.get("reason"), "deduplication reason")
    for round_record in _list(corpus.get("citation_rounds"), "citation_rounds"):
        round_record = _mapping(round_record, "citation round")
        number = round_record.get("round")
        if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= planned["citation_policy"]["max_rounds"]:
            raise ValueError("citation round exceeds the predeclared bound")
        if round_record.get("direction") not in planned["citation_policy"]["directions"]:
            raise ValueError("citation direction was not declared")
        if not _strings(round_record.get("seed_ids"), "citation seed_ids"):
            raise ValueError("citation round must identify its seeds")
        _strings(round_record.get("found_ids"), "citation found_ids")
        _date(round_record.get("executed_at"), "citation.executed_at")
    for challenge in _list(corpus.get("challenges"), "challenges"):
        challenge = _mapping(challenge, "challenge")
        if challenge.get("type") not in CHALLENGES:
            raise ValueError("unknown challenge query type")
        _text(challenge.get("query"), "challenge.query")
        if challenge.get("source") not in planned["sources"]:
            raise ValueError("challenge source was not declared")
        _date(challenge.get("executed_at"), "challenge.executed_at")
        _strings(challenge.get("found_ids"), "challenge.found_ids")
    coverage = _mapping(corpus.get("coverage"), "coverage")
    dimensions = _mapping(coverage.get("dimensions"), "coverage.dimensions")
    if not dimensions:
        raise ValueError("coverage must name dimensions such as robot, task, setting or mechanism")
    if not _strings(coverage.get("limits"), "coverage.limits"):
        raise ValueError("coverage must disclose actual limits")
    _strings(coverage.get("unsearched"), "coverage.unsearched")
    included = {paper["paper_id"] for paper in corpus["papers"] if paper["decision"] == "include"}
    matrix_seen = set()
    for row in _list(corpus.get("evidence_matrix"), "evidence_matrix"):
        row = _mapping(row, "evidence matrix row")
        paper_id = _text(row.get("paper_id"), "evidence.paper_id")
        if paper_id not in included or paper_id in matrix_seen:
            raise ValueError("evidence matrix must refer to distinct included corpus papers")
        matrix_seen.add(paper_id)
        _text(row.get("note_path"), "evidence.note_path")
        _text(row.get("finding"), "evidence.finding")
        if row.get("position") not in CHALLENGES or not isinstance(row.get("critical"), bool):
            raise ValueError("evidence position or critical flag is invalid")
        if "verification" in row:
            _list(row["verification"], "evidence.verification")
    removed = {item["removed"] for item in dedup["duplicates"]}
    discovered = set(planned["seed_papers"])
    for group, field in (("searches", "returned_ids"), ("citation_rounds", "found_ids"), ("challenges", "found_ids")):
        for entry in corpus[group]:
            discovered.update(entry[field])
    if discovered - identities - removed:
        raise ValueError("discovered candidates must have screening or explicit deduplication decisions")
    if identities - discovered:
        raise ValueError("corpus paper lacks seed, query or citation provenance")
    canonical(corpus)
    return {"protocol": planned, "corpus": corpus}


def freeze(settings, path, apply=False, previous=None, reason=None):
    record = read_record(settings.resolve(str(path)), settings.vault)
    corpus = load_corpus(settings, record.data)
    content = corpus_content(record.data, corpus)
    receipts = history(settings, "corpus", record.data["review_id"])
    if receipts and digest(content) != receipts[-1]["snapshot_digest"]:
        old_version = receipts[-1]["snapshot"]["protocol"]["version"]
        if old_version == content["protocol"]["version"]:
            raise ValueError("changed corpus requires a new protocol version")
    result = create_receipt(settings, kind="corpus", object_id=record.data["review_id"],
                            source=record.relative, content=content, apply=apply,
                            previous=previous, reason=reason)
    result["metadata"] = {"corpus_digest": result["digest"], "corpus_receipt": result["receipt"]}
    return result


def _external_gate(corpus):
    searches = corpus["searches"]
    families = {row["family_id"] for row in searches}
    queries = {row["query"].casefold().strip() for row in searches}
    if len(families) < 2 or len(queries) < 2:
        raise ValueError("externally_checked requires actually executed distinct query families")
    if not corpus["deduplication"]["performed"]:
        raise ValueError("externally_checked requires completed deduplication")
    if {row["type"] for row in corpus["challenges"]} != CHALLENGES:
        raise ValueError("externally_checked requires all five challenge query types")
    if len({row["query"].casefold().strip() for row in corpus["challenges"]}) < len(CHALLENGES):
        raise ValueError("challenge types require distinct executed queries")
    if any(paper["decision"] == "pending" for paper in corpus["papers"]):
        raise ValueError("externally_checked cannot conceal pending screening decisions")
    if not corpus["citation_rounds"] and not corpus["coverage"]["unsearched"]:
        raise ValueError("omitted citation work must be disclosed in coverage.unsearched")


def check(settings, records):
    issues = []
    protocols, valid = {}, {}
    for record in records:
        if record.data.get("type") != "review-protocol":
            continue
        data = record.data
        try:
            review_id = _text(data.get("review_id"), "review_id")
            if review_id in protocols:
                raise ValueError("duplicate review_id")
            protocols[review_id] = record
            corpus = load_corpus(settings, data)
            content = corpus_content(data, corpus)
            receipts = history(settings, "corpus", review_id)
            if not data.get("corpus_digest") and not data.get("corpus_receipt"):
                if receipts:
                    raise ValueError("corpus receipt history exists but page references were removed")
                continue
            receipt = read_receipt(settings, data["corpus_receipt"])
            if receipt["kind"] != "corpus" or receipt["object_id"] != review_id:
                raise ValueError("corpus receipt belongs to a different review")
            if not receipts or receipt != receipts[-1]:
                raise ValueError("protocol must reference the latest corpus revision")
            if data.get("corpus_digest") != receipt["snapshot_digest"] or digest(content) != receipt["snapshot_digest"]:
                raise ValueError("corpus or protocol changed after freeze; create an explicit revision")
            valid[review_id] = receipts
        except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
            issues.append(diagnostic("review.protocol", record.relative, str(exc)))
    by_path = {record.relative: record for record in records}
    for record in records:
        if record.data.get("type") != "research-gap":
            continue
        data = record.data
        if data.get("review_status") != "externally_checked" and data.get("confidence") != "high":
            continue
        try:
            if data.get("review_status") != "externally_checked":
                raise ValueError("high-confidence gap requires external review evidence")
            review_id = _text(data.get("review_id"), "gap.review_id")
            if review_id not in valid:
                raise ValueError("gap must resolve to a valid frozen review corpus")
            fingerprint = _text(data.get("corpus_digest"), "gap.corpus_digest")
            receipt = next((item for item in valid[review_id] if item["snapshot_digest"] == fingerprint), None)
            if receipt is None:
                raise ValueError("gap corpus digest has no receipt in its review history")
            snapshot = receipt["snapshot"]
            protocol = _mapping(snapshot.get("protocol"), "frozen protocol")
            corpus = _mapping(snapshot.get("corpus"), "frozen corpus")
            if protocol.get("review_id") != review_id:
                raise ValueError("gap corpus receipt belongs to a different review")
            corpus_content({"type": "review-protocol", **protocol}, corpus)
            _external_gate(corpus)
            if data.get("confidence") == "high":
                ids = set(_strings(data.get("evidence_ids"), "gap.evidence_ids"))
                critical = {row["paper_id"]: row for row in corpus["evidence_matrix"] if row["critical"]}
                if not critical or not ids or not ids <= set(critical):
                    raise ValueError("high-confidence gap needs explicit links to critical corpus evidence")
                for paper_id in ids:
                    row = critical[paper_id]
                    note = by_path.get(row["note_path"])
                    if note is None or note.data.get("type") != "literature-note":
                        raise ValueError("critical evidence must resolve to an actual Paper Note")
                    expected = {"doi:" + doi(note.data.get("doi")),
                                "arxiv:" + str(note.data.get("arxiv_id", "")),
                                "zotero:" + ("user:local" if note.data.get("library_id") is None else "group:" + str(note.data["library_id"])) + ":" + str(note.data.get("zotero_key", ""))}
                    if paper_id not in expected:
                        raise ValueError("critical corpus identity differs from its linked Note")
                    if row.get("evidence_status") not in {"pdf_verified", "fulltext_verified"}:
                        raise ValueError("critical evidence needs source-level verification")
                    from .validation import verify_claim
                    evidence = {"source_notes": [row["note_path"]], "evidence_status": row["evidence_status"],
                                "verification": row.get("verification", []), "page_path": record.relative}
                    failures = verify_claim(settings, evidence, records)
                    if failures:
                        raise ValueError("critical evidence verification failed: " + "; ".join(item["detail"] for item in failures))
        except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
            issues.append(diagnostic("review.gap-gate", record.relative, str(exc)))
    return issues
