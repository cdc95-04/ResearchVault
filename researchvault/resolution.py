"""Resolve selected public identifiers into source-bound metadata candidates.

No PDF or Zotero write occurs here. Captured HTML is evidence from the actual
response, never generated citation markup. The acquisition caller must bind the
downloaded PDF SHA-256 before source-bound PDF verification can succeed.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import quote, unquote, urlencode, urlsplit
import xml.etree.ElementTree as ET

from . import discovery
from .pdf_identity import _CitationHTML, _author, _compact, _pdf_destination, _source_kind

_MODERN_ARXIV = re.compile(r"(\d{4}\.\d{4,5})(v[1-9]\d*)?\Z", re.I)
_LEGACY_ARXIV = re.compile(r"[a-z-]+(?:\.[a-z]{2})?/\d{7}(?:v[1-9]\d*)?\Z", re.I)
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


def _doi(value):
    return discovery.normalize_doi(unicodedata.normalize("NFKC", value))


def _arxiv(value):
    value = value.removesuffix(".pdf")
    if _LEGACY_ARXIV.fullmatch(value):
        raise ValueError("Legacy arXiv identifiers are unsupported; manual review is required")
    match = _MODERN_ARXIV.fullmatch(value)
    if not match:
        raise ValueError("A complete modern arXiv identifier is required")
    base, suffix = match.groups()
    # The month is part of the identifier, not an arbitrary four-digit prefix.
    if not 1 <= int(base[2:4]) <= 12:
        raise ValueError("The arXiv identifier has an invalid month")
    exact = base + (suffix.lower() if suffix else "")
    return {"kind": "arxiv", "arxiv_id": base,
            "arxiv_id_version": exact if suffix else None,
            "requested_version": suffix[1:] if suffix else None,
            "canonical_id": "arxiv:" + exact,
            "canonical_url": "https://arxiv.org/abs/" + exact}


def _doi_identity(value):
    value = _doi(value)
    registered = re.fullmatch(r"10\.48550/arxiv\.(.+)", value, re.I)
    if registered:
        result = _arxiv(registered.group(1))
        result["registered_doi"] = value
        return result
    return {"kind": "doi", "doi": value, "canonical_id": "doi:" + value,
            "canonical_url": "https://doi.org/" + quote(value, safe="/")}


def parse(raw):
    """Parse supported identities without I/O; reject unknown URLs before fetch."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Supply a DOI, arXiv identifier or supported official paper URL")
    value = unicodedata.normalize("NFKC", raw).strip()
    if any(ord(character) < 32 for character in value):
        raise ValueError("Identifier contains control characters")
    if re.match(r"^arxiv\s*:", value, re.I):
        return _arxiv(re.sub(r"^arxiv\s*:\s*", "", value, flags=re.I))
    if re.match(r"^doi\s*:", value, re.I):
        return _doi_identity(re.sub(r"^doi\s*:\s*", "", value, flags=re.I))
    if re.match(r"^https?://", value, re.I):
        url = urlsplit(value)
        if url.username or url.password or url.port not in (None, 443) or url.query or url.fragment:
            raise ValueError("Identifier URLs must not contain credentials, query/tracking parameters or fragments")
        host = (url.hostname or "").lower()
        if host in {"doi.org", "dx.doi.org"}:
            return _doi_identity(unquote(url.path.lstrip("/")))
        if host == "arxiv.org":
            match = re.fullmatch(r"/(?:abs|pdf)/(.+)", url.path)
            if not match:
                raise ValueError("Use an arXiv abs or PDF paper URL")
            return _arxiv(unquote(match.group(1)))
        if url.scheme.lower() != "https":
            raise ValueError("Official publisher URLs require HTTPS")
        canonical = "https://" + host + url.path
        try:
            kind = _source_kind(canonical)
        except ValueError:
            raise ValueError("Unsupported paper URL; use a DOI, arXiv ID or supported official landing URL") from None
        if kind == "arxiv":
            raise ValueError("Use an arXiv abs or PDF paper URL")
        return {"kind": "publisher", "publisher": kind,
                "canonical_id": "url:" + canonical, "canonical_url": canonical}
    if value.startswith("10."):
        return _doi_identity(value)
    return _arxiv(value)


def _source(url, response, retrieved_at):
    digest = hashlib.sha256(response.body).hexdigest()
    return {"url": url, "sha256": digest, "response_sha256": digest,
            "digest_scope": "response_bytes",
            "media_type": response.header("Content-Type").split(";", 1)[0].strip().lower(),
            "retrieved_at": retrieved_at}


def _capture(url, *, transport=None, html=False):
    sender = transport or discovery.public_request

    def exact_source(method, requested, **kwargs):
        # Validate before the injected/live sender sees a redirect destination.
        # Official source identity is the exact selected endpoint, including the
        # arXiv id_list query and its fixed version, not any public HTTPS page.
        if requested != url:
            raise ValueError("Official metadata redirected away from its selected exact source URL")
        return sender(method, requested, **kwargs)

    response, final = discovery.get(url, transport=exact_source, max_bytes=1_000_000)
    if final != url:
        raise ValueError("Official metadata redirected away from its selected exact source URL")
    media = response.header("Content-Type").split(";", 1)[0].strip().lower()
    accepted = {"text/html", "application/xhtml+xml"} if html else {"application/atom+xml", "application/xml", "text/xml"}
    if media not in accepted:
        raise ValueError("Official metadata response has an unexpected content type")
    try:
        text = response.body.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Official metadata must be usable UTF-8 text") from None
    timestamp = discovery.now()
    capture = _source(url, response, timestamp)
    # Decoding UTF-8 with a BOM normalizes the text while response_sha256 still
    # binds the original received bytes. The verifier hashes captured HTML text.
    capture["text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text, timestamp, capture


def _one(meta, key, required=True):
    values = list(dict.fromkeys(value.strip() for value in meta.get(key, []) if value.strip()))
    if len(values) > 1 or required and not values:
        raise ValueError("Official metadata is missing or conflicting: " + key)
    return values[0] if values else None


def _citation(html):
    parser = _CitationHTML()
    parser.feed(html)
    title = _one(parser.meta, "citation_title")
    authors = parser.meta.get("citation_author", [])
    if not authors or any(not author.strip() for author in authors):
        raise ValueError("Official metadata requires the complete author list")
    return parser.meta, title, authors


def _year(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}(?:[-/]\d{2}(?:[-/]\d{2})?)?", value):
        raise ValueError("Official metadata requires a publication date")
    year = int(value[:4])
    if not 1000 <= year <= 9999:
        raise ValueError("Invalid publication year")
    return year


def _official_pdf(kind, source, pdf):
    discovery.public_url(pdf)
    if _pdf_destination(kind, source, pdf):
        return True
    # PMLR also serves its official repository PDFs under its own paper path.
    if kind == "pmlr":
        landing = urlsplit(source)
        volume, stem = re.fullmatch(r"/v(\d+)/([\w-]+)\.html", landing.path).groups()
        return pdf == f"https://proceedings.mlr.press/v{volume}/{stem}/{stem}.pdf"
    return False


def _route(url, version, source, license=None):
    return {"url": url, "version": version, "method": "official_open_access",
            "license": license, "source_url": source}


def _resolve_arxiv(identity, transport):
    requested = identity["arxiv_id_version"] or identity["arxiv_id"]
    api = "https://export.arxiv.org/api/query?" + urlencode({"id_list": requested})
    atom, _, atom_source = _capture(api, transport=transport)
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", atom, re.I):
        raise ValueError("DTD/entity declarations are prohibited in metadata")
    try:
        feed = ET.fromstring(atom)
    except ET.ParseError:
        raise ValueError("Official arXiv Atom metadata cannot be parsed") from None
    entries = feed.findall(_ATOM + "entry")
    if len(entries) != 1:
        raise ValueError("arXiv metadata must identify exactly one paper")
    entry = entries[0]
    returned = parse(entry.findtext(_ATOM + "id", ""))
    exact = returned.get("arxiv_id_version")
    if returned["kind"] != "arxiv" or not exact or returned["arxiv_id"] != identity["arxiv_id"]:
        raise ValueError("arXiv metadata disagrees with the selected identity or lacks an exact version")
    if identity["arxiv_id_version"] and exact != identity["arxiv_id_version"]:
        raise ValueError("arXiv metadata returned another selected version")
    atom_title = " ".join(entry.findtext(_ATOM + "title", "").split())
    atom_authors = [" ".join(author.findtext(_ATOM + "name", "").split()) for author in entry.findall(_ATOM + "author")]
    if not atom_title or not atom_authors or not all(atom_authors):
        raise ValueError("Official arXiv metadata lacks title or complete authors")
    source = "https://arxiv.org/abs/" + exact
    html, timestamp, html_source = _capture(source, transport=transport, html=True)
    meta, title, authors = _citation(html)
    if _compact(title) != _compact(atom_title) or [_author(author) for author in authors] != [_author(author) for author in atom_authors]:
        raise ValueError("arXiv Atom and captured HTML title/author identities disagree")
    source_id = _one(meta, "citation_arxiv_id")
    if source_id not in {exact, identity["arxiv_id"]}:
        raise ValueError("Captured arXiv HTML belongs to another identifier")
    year = _year(_one(meta, "citation_online_date"))
    linked_pdf = _one(meta, "citation_pdf_url")
    base_pdf = "https://arxiv.org/pdf/" + identity["arxiv_id"]
    if linked_pdf.removesuffix(".pdf") not in {base_pdf, base_pdf + exact[len(identity["arxiv_id"]):]}:
        raise ValueError("Captured arXiv HTML links another paper PDF")
    pdf = "https://arxiv.org/pdf/" + exact
    version = "arxiv:" + exact
    related = entry.findtext(_ARXIV + "doi")
    related_doi = _doi(related) if related and related.strip() else None
    evidence = {"source_url": source, "html": html, "html_sha256": html_source["text_sha256"],
                "retrieved_at": timestamp, "pdf_url": pdf, "version": version}
    return {"canonical_id": version, "doi": None, "title": title, "authors": authors,
            "year": year, "arxiv_id": identity["arxiv_id"], "arxiv_id_version": exact,
            "related_doi": related_doi, "version": version, "expected_version": version,
            "canonical_url": source, "source_url": source, "retrieved_at": timestamp,
            "sources": [atom_source, html_source], "source_evidence": evidence,
            "lawful_routes": [_route(pdf, version, source)], "identity_status": "VERIFIED_METADATA",
            "selected_for_acquisition": False}


def _resolve_publisher(identity, transport):
    source, kind = identity["canonical_url"], identity["publisher"]
    html, timestamp, capture = _capture(source, transport=transport, html=True)
    meta, title, authors = _citation(html)
    year = _year(_one(meta, "citation_publication_date"))
    pdf = _one(meta, "citation_pdf_url")
    if not _official_pdf(kind, source, pdf):
        raise ValueError("Official source PDF link does not belong to the selected paper")
    doi = _one(meta, "citation_doi", required=False)
    doi = _doi(doi) if doi else None
    version = "acceptedVersion" if kind == "cvf" else "publishedVersion"
    evidence = {"source_url": source, "html": html, "html_sha256": capture["text_sha256"],
                "retrieved_at": timestamp, "pdf_url": pdf, "version": version}
    sources = [capture]
    if kind == "cvf":
        edition = re.search(r"/content/(CVPR\d{4})/", source).group(1)
        policy_url = "https://openaccess.thecvf.com/" + edition
        policy, policy_time, policy_source = _capture(policy_url, transport=transport, html=True)
        parser = _CitationHTML(); parser.feed(policy)
        policy_text = " ".join(" ".join(parser.text).split())
        if not (re.search(r"identical to the accepted version(?:s)?", policy_text, re.I) and
                re.search(r"final published version.*?IEEE Xplore", policy_text, re.I)):
            raise ValueError("Official CVF policy does not substantiate the accepted OA version")
        evidence.update(policy_url=policy_url, policy_html=policy, policy_retrieved_at=policy_time)
        sources.append(policy_source)
    candidate = {"canonical_id": "doi:" + doi if doi else identity["canonical_id"],
                 "doi": doi, "title": title, "authors": authors, "year": year,
                 "version": version, "expected_version": version, "publisher": kind,
                 "canonical_url": source, "url": source, "source_url": source,
                 "retrieved_at": timestamp, "sources": sources, "source_evidence": evidence,
                 "lawful_routes": [_route(pdf, version, source, _one(meta, "citation_license", required=False))],
                 "identity_status": "VERIFIED_METADATA", "selected_for_acquisition": False}
    if kind in {"neurips", "iclr"}:
        candidate["conference_year"] = int(re.search(r"/paper/(\d{4})/", source).group(1))
    return candidate


def _resolve_doi(identity, transport):
    captures = []
    sender = transport or discovery.public_request
    expected = "https://api.crossref.org/works/" + quote(identity["doi"], safe="")

    def capture(method, url, **kwargs):
        if url != expected:
            raise ValueError("Canonical DOI metadata redirected away from its exact Crossref endpoint")
        response = sender(method, url, **kwargs)
        if response.status == 200:
            captures.append(_source(url, response, discovery.now()))
        return response

    candidate = discovery.lookup(identity["doi"], transport=capture)
    if (not isinstance(candidate.get("title"), str) or not candidate["title"].strip() or
            not isinstance(candidate.get("authors"), list) or not candidate["authors"] or
            any(not isinstance(author, str) or not author.strip() for author in candidate["authors"]) or
            type(candidate.get("year")) is not int or not 1000 <= candidate["year"] <= 9999):
        raise ValueError("Canonical DOI metadata lacks usable title, complete authors or year")
    candidate.update(canonical_url=identity["canonical_url"], retrieved_at=discovery.now(),
                     sources=captures, lawful_routes=[], expected_version=None,
                     arxiv_id_version=None)
    return candidate


def resolve(raw, *, transport=None):
    """Resolve one explicitly supplied identity through bounded public GET reads."""
    identity = parse(raw)
    if identity["kind"] == "arxiv":
        return _resolve_arxiv(identity, transport)
    if identity["kind"] == "publisher":
        return _resolve_publisher(identity, transport)
    return _resolve_doi(identity, transport)
