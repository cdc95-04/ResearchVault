"""Selected public OA acquisition with per-paper, resumable external state."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import quote, urlencode

from .discovery import duplicates, get, get_json, normalize_doi, now, public_url
from .safety import require_writable

PDF_STATES = {"VERIFIED", "PROBABLE", "AMBIGUOUS", "SUPPLEMENT", "WRONG", "CORRUPTED"}
VERSIONS = {"submittedVersion", "acceptedVersion", "publishedVersion"}


def _words(text):
    return " ".join(re.findall(r"\w+", str(text).casefold()))


def assess_identity(first_page, metadata, candidate, *, structurally_valid=True):
    """Conservative heuristic; only primary identity text before references is used."""
    if not structurally_valid:
        return {"status": "CORRUPTED", "reason": "PDF parser could not validate the document"}
    primary = re.split(r"(?im)^\s*(?:references|bibliography|literature cited)\s*$", first_page)[0]
    front = primary[:16000]
    heading = front[:1500] + " " + str(metadata.get("title", ""))
    if re.search(r"\b(supplement(?:ary|al)?|supporting information|appendix only)\b", heading, re.I):
        return {"status": "SUPPLEMENT", "reason": "Document is marked as supplementary material"}
    version_labels = {
        "submittedVersion": r"\b(?:preprint|submitted manuscript|not peer reviewed)\b",
        "acceptedVersion": r"\b(?:accepted manuscript|author accepted manuscript|postprint)\b",
        "publishedVersion": r"\b(?:version of record|published version)\b",
    }
    versions = [name for name, pattern in version_labels.items() if re.search(pattern, front[:4000], re.I)]
    observed_version = versions[0] if len(versions) == 1 else None
    expected_version = candidate.get("expected_version")
    if len(versions) > 1 or expected_version and observed_version and expected_version != observed_version:
        return {"status": "AMBIGUOUS", "reason": "Document version labels conflict with the selected version", "observed_version": observed_version}
    doi = normalize_doi(candidate["doi"])
    found = {m.rstrip(".,;)").lower() for m in re.findall(r"10\.\d{4,9}/[^\s<>\"\x00-\x1f]+", front)}
    declared = str(metadata.get("doi", "")).strip()
    if declared:
        try:
            found.add(normalize_doi(declared))
        except ValueError:
            pass
    # A title mentioned later in the first-page discussion is not the document heading.
    title_match = _words(candidate["title"]) in _words(front[:1500])
    metadata_title = _words(metadata.get("title", ""))
    if metadata_title and metadata_title == _words(candidate["title"]):
        title_match = True
    author_match = any(_words(a) and _words(a) in _words(front + " " + str(metadata.get("author", ""))) for a in candidate.get("authors", []))
    year_match = str(candidate.get("year")) in front
    if found and doi not in found:
        return {"status": "WRONG", "reason": "Primary DOI disagrees with the selected publication"}
    if doi in found and len(found) == 1 and title_match and author_match and year_match:
        if not observed_version:
            return {"status": "PROBABLE", "reason": "Main-document identity agrees but publication version is unverified"}
        return {"status": "VERIFIED", "reason": "Main-document DOI, title, author, year and explicit version label agree", "observed_version": observed_version}
    if doi in found and len(found) > 1:
        return {"status": "AMBIGUOUS", "reason": "Multiple primary DOI identities require review"}
    if title_match and author_match:
        return {"status": "PROBABLE", "reason": "Title/author match lacks complete primary DOI/year evidence"}
    return {"status": "AMBIGUOUS", "reason": "Insufficient main-document identity evidence"}


def verify_pdf(content, candidate):
    if isinstance(candidate, dict) and "source_evidence" in candidate:
        # Explicit captured-source review supplements first-page DOI matching;
        # a failed evidence packet must never fall back to a weaker result.
        from .pdf_identity import verify_source_pdf
        return verify_source_pdf(content, candidate, candidate["source_evidence"])
    if not content.startswith(b"%PDF-"):
        return {"status": "CORRUPTED", "reason": "Missing PDF signature"}
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"status": "AMBIGUOUS", "reason": "Optional pypdf is unavailable; identity was not verified"}
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted or not reader.pages:
            raise ValueError("Encrypted or empty PDF")
        page = reader.pages[0].extract_text() or ""
        info = reader.metadata or {}
        metadata = {"title": info.get("/Title", ""), "author": info.get("/Author", ""), "doi": info.get("/doi", "")}
        return assess_identity(page, metadata, candidate)
    except Exception:
        return {"status": "CORRUPTED", "reason": "PDF parsing failed; no identity claim made"}


def oa_locations(doi, email, *, transport=None):
    doi = normalize_doi(doi)
    if not email or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Unpaywall requires an explicit contact email")
    url = "https://api.unpaywall.org/v2/" + quote(doi, safe="") + "?" + urlencode({"email": email})
    data = get_json(url, transport=transport)
    if normalize_doi(data.get("doi")) != doi:
        raise ValueError("Unpaywall returned another publication")
    if not data.get("is_oa") or data.get("is_paratext"):
        return []
    locations, seen = [], set()
    for location in [data.get("best_oa_location")] + list(data.get("oa_locations") or []):
        if not location or not location.get("url_for_pdf") or location.get("host_type") not in {"publisher", "repository"}:
            continue
        pdf_url = location["url_for_pdf"]
        if pdf_url in seen:
            continue
        public_url(pdf_url)
        seen.add(pdf_url)
        locations.append({k: location.get(k) for k in ("url_for_pdf", "url_for_landing_page", "license", "version", "host_type")})
    return locations


def _save(path, data):
    temporary = path.with_suffix(".pending")
    if path.is_symlink() or temporary.is_symlink():
        raise ValueError("State files cannot be symbolic links")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run(settings, candidates, *, selected, enabled=False, email=None, transport=None, verifier=None):
    require_writable(settings, 'Fulltext acquisition')
    if not enabled:
        return {"status": "DISABLED", "papers": []}
    if settings.runtime is None:
        raise ValueError("Acquisition requires an explicit runtime outside the Vault")
    runtime, vault = Path(settings.runtime).resolve(), Path(settings.vault).resolve()
    if runtime == vault or vault in runtime.parents or runtime in vault.parents:
        raise ValueError("Runtime and Vault roots must not overlap")
    options = getattr(settings, "options", {}).get("acquisition", {})
    max_bytes, interval = options.get("max_bytes", 100 * 1024 * 1024), options.get("interval", 1.0)
    if type(max_bytes) is not int or max_bytes < 1 or type(interval) not in (int, float) or not math.isfinite(interval) or interval < 0:
        raise ValueError("Acquisition limits must be positive bytes and finite nonnegative interval")
    directory = runtime / "intake"
    directory.mkdir(parents=True, exist_ok=True)
    if directory.resolve().parent != runtime:
        raise ValueError("Intake state escaped the runtime")
    selected = {normalize_doi(str(v).removeprefix("doi:")) for v in selected}
    grouped = {doi: [] for doi in selected}
    for candidate in candidates:
        try:
            doi = normalize_doi(candidate.get("doi"))
        except (ValueError, AttributeError):
            continue
        if doi in grouped:
            grouped[doi].append(candidate)
    work, results = [], []
    for doi in sorted(selected):
        try:
            if not grouped[doi]:
                raise ValueError("Selected DOI has no candidate metadata")
            unique, _ = duplicates(grouped[doi])
            work.extend(unique)
        except ValueError as exc:
            blocked = {"doi": doi, "status": "AMBIGUOUS", "reason": str(exc), "auto_ingest": False, "updated_at": now()}
            _save(directory / (hashlib.sha256((doi + "\nblocked").encode()).hexdigest() + ".json"), blocked)
            results.append(blocked)
    attempted = False
    for candidate in work:
        doi = normalize_doi(candidate["doi"])
        if doi not in selected:
            continue
        identity = json.dumps({k: candidate.get(k) for k in ("doi", "title", "authors", "year", "version", "expected_version", "relations")}, sort_keys=True, ensure_ascii=False).encode()
        token = hashlib.sha256((doi + "\n" + str(candidate.get("version"))).encode()).hexdigest()
        state_path, pdf_path = directory / (token + ".json"), directory / (token + ".pdf")
        if state_path.is_symlink() or pdf_path.is_symlink():
            raise ValueError("Intake files cannot be symbolic links")
        fingerprint = hashlib.sha256(identity).hexdigest()
        state = {"doi": doi, "candidate_sha256": fingerprint, "status": "RESOLVING", "updated_at": now()}
        if candidate.get("identity_status") != "VERIFIED_METADATA" or candidate.get("canonical_id") != "doi:" + doi or not all(candidate.get(k) for k in ("title", "authors", "year")):
            state.update(status="AMBIGUOUS", reason="Acquisition requires canonical verified title/author/year metadata", auto_ingest=False)
            if not state_path.exists():
                _save(state_path, state)
            results.append(state)
            continue
        if state_path.exists():
            old = json.loads(state_path.read_text(encoding="utf-8"))
            if old.get("candidate_sha256") != fingerprint:
                raise ValueError("Resume metadata changed; review the prior intake state")
            if old.get("status") in PDF_STATES:
                if not old.get("filename"):
                    results.append(old)
                    continue
                if pdf_path.exists() and hashlib.sha256(pdf_path.read_bytes()).hexdigest() == old.get("sha256"):
                    results.append(old)
                    continue
                raise ValueError("Saved intake PDF is missing or has changed")
        _save(state_path, state)
        try:
            if attempted and interval:
                time.sleep(interval)
            attempted = True
            routes = oa_locations(doi, email, transport=transport)
            if not routes:
                state.update(status="UNAVAILABLE", reason="No lawful public OA PDF route")
            else:
                route = routes[0]
                expected_version = candidate.get("expected_version") or (candidate.get("version") if candidate.get("version") in VERSIONS else route.get("version"))
                state.update(status="DOWNLOADING", route=route)
                _save(state_path, state)
                response, final_url = get(route["url_for_pdf"], transport=transport, max_bytes=max_bytes)
                media = response.header("Content-Type").split(";", 1)[0].lower()
                if media not in {"application/pdf", "application/octet-stream"} or not response.body.startswith(b"%PDF-"):
                    verdict = {"status": "CORRUPTED", "reason": "Response type or PDF signature is invalid"}
                else:
                    verdict = (verifier or verify_pdf)(response.body, {**candidate, "expected_version": expected_version})
                if verdict.get("status") not in PDF_STATES:
                    raise ValueError("Verifier returned an unsupported status")
                if verdict["status"] == "VERIFIED":
                    observed = verdict.get("observed_version")
                    expected = expected_version
                    if not expected or not observed:
                        verdict = {"status": "PROBABLE", "reason": "Publication version lacks explicit verification"}
                    elif observed != expected or route.get("version") != observed:
                        verdict = {"status": "AMBIGUOUS", "reason": "PDF, selected and OA route versions disagree", "observed_version": observed}
                if pdf_path.exists():
                    if pdf_path.read_bytes() != response.body:
                        raise ValueError("Existing intake artifact conflicts; no overwrite allowed")
                else:
                    with pdf_path.open("xb") as stream:
                        stream.write(response.body)
                        stream.flush()
                        os.fsync(stream.fileno())
                state.update(verdict, sha256=hashlib.sha256(response.body).hexdigest(), filename=pdf_path.name,
                             bytes=len(response.body), final_url=final_url,
                             version_provenance={"candidate_version": candidate.get("version"), "oa_version": route.get("version"), "source": "Unpaywall route metadata"},
                             auto_ingest=verdict["status"] == "VERIFIED")
        except Exception as exc:
            # Exception messages can contain URLs or credentials; retain only the class.
            state.update(status="FAILED", reason=type(exc).__name__, auto_ingest=False)
        state["updated_at"] = now()
        _save(state_path, state)
        results.append(state)
    return {"status": "COMPLETE", "papers": results}
