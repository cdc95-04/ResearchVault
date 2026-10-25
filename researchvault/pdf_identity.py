"""Explicit, source-bound PDF identity review without network or filesystem I/O.

This supplements the unchanged first-page-only acquisition verifier. The caller
must capture official HTML through the existing lawful acquisition transport.
The evidence packet binds that capture and its exact PDF URL to downloaded bytes;
it is not an authenticity signature or a human scientific review.

Evidence fields: source_url, html, retrieved_at (timezone-aware ISO timestamp),
pdf_url, sha256, version. CVF accepted copies additionally require policy_url,
policy_html and policy_retrieved_at. Versions are publishedVersion,
acceptedVersion, or arxiv:<identifier>v<version>. Candidate authors/year describe
the acquired version; conference_year may differ from its publication year.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
from html.parser import HTMLParser
import io
import re
import unicodedata
from urllib.parse import urlsplit

from .discovery import normalize_doi


class _CitationHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag.casefold() != "meta":
            return
        fields = dict(attrs)
        name = str(fields.get("name", "")).casefold()
        if name.startswith("citation_") and fields.get("content") is not None:
            self.meta.setdefault(name, []).append(fields["content"].strip())

    def handle_data(self, data):
        self.text.append(data)


def _compact(text):
    """Ignore extraction whitespace, punctuation and decomposed accent marks."""
    value = unicodedata.normalize("NFKD", str(text)).casefold().replace("ı", "i")
    return "".join(character for character in value if character.isalnum())


def _author(value):
    pieces = str(value).split(",", 1)
    return _compact(" ".join(reversed(pieces)) if len(pieces) == 2 else value)


def _name_tokens(value):
    pieces = str(value).split(",", 1)
    ordered = " ".join(reversed(pieces)) if len(pieces) == 2 else str(value)
    return [_compact(token) for token in ordered.split()]


def _one(meta, key):
    values = list(dict.fromkeys(meta.get(key, [])))
    return values[0] if len(values) == 1 else None


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except (TypeError, ValueError):
        return False


def _url(value):
    parsed = urlsplit(str(value))
    if (parsed.scheme != "https" or parsed.username or parsed.password or
            parsed.port not in (None, 443) or parsed.query or parsed.fragment):
        raise ValueError("Evidence requires an exact public HTTPS URL")
    return parsed.hostname, parsed.path


def _source_kind(url):
    host, path = _url(url)
    if host == "arxiv.org" and re.fullmatch(r"/abs/\d{4}\.\d{4,5}v[1-9]\d*", path):
        return "arxiv"
    if host in {"proceedings.neurips.cc", "proceedings.iclr.cc"} and re.fullmatch(
            r"/paper_files/paper/\d{4}/hash/[a-f0-9]{32}-Abstract-[\w-]+\.html", path):
        return "neurips" if host == "proceedings.neurips.cc" else "iclr"
    if host == "proceedings.mlr.press" and re.fullmatch(r"/v\d+/[\w-]+\.html", path):
        return "pmlr"
    if host == "openaccess.thecvf.com" and re.fullmatch(
            r"/content/CVPR\d{4}/html/[\w-]+_paper\.html", path):
        return "cvf"
    raise ValueError("Unsupported or unversioned official identity source")


def _pdf_destination(kind, source, destination):
    host, path = _url(destination)
    source_host, source_path = _url(source)
    if kind == "arxiv":
        return host == "arxiv.org" and bool(re.fullmatch(r"/pdf/\d{4}\.\d{4,5}(?:v[1-9]\d*)?(?:\.pdf)?", path))
    if kind in {"neurips", "iclr"}:
        prefix, filename = source_path.rsplit("/hash/", 1)
        identity = filename[:32]
        return host == source_host and bool(re.fullmatch(
            re.escape(prefix + "/file/" + identity) + r"-Paper-[\w-]+\.pdf", path))
    if kind == "cvf":
        return host == source_host and path == source_path.replace("/html/", "/papers/").removesuffix(".html") + ".pdf"
    volume, stem = re.fullmatch(r"/v(\d+)/([\w-]+)\.html", source_path).groups()
    return ((host == "proceedings.mlr.press" and path == f"/v{volume}/{stem}/{stem}.pdf") or
            (host == "raw.githubusercontent.com" and path == f"/mlresearch/v{volume}/main/assets/{stem}/{stem}.pdf"))


def _heading_matches(first_page, title):
    # Match complete consecutive title lines, never a substring of a longer title
    # or a title cited in the abstract. This also joins split small-cap glyphs.
    heading = re.split(r"(?im)^\s*abstract\s*:?\s*$", first_page, maxsplit=1)[0]
    lines = [line.strip() for line in heading[:1800].splitlines() if line.strip()][:12]
    expected = _compact(title)
    return bool(expected) and any(
        _compact(" ".join(lines[start:end])) == expected
        for start in range(len(lines))
        for end in range(start + 1, min(len(lines), start + 8) + 1)
    )


def _doi_value(value):
    try:
        return normalize_doi(value)
    except (TypeError, ValueError):
        return None


def verify_source_pdf(content, candidate, evidence):
    """Review actual bytes against an explicit captured official identity packet.

    Missing evidence fails closed as AMBIGUOUS; positive contradictory identity
    fails as WRONG. Only calculated checks produce VERIFIED. No state is edited.
    """
    checks = {}
    anchor = {}

    def result(status, reason, **extra):
        return {"status": status, "reason": reason, "checks": dict(checks),
                "source_anchor": dict(anchor), **extra}

    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        return result("CORRUPTED", "Missing PDF signature")
    try:
        from pypdf import PdfReader
    except ImportError:
        return result("AMBIGUOUS", "Optional pypdf is unavailable")
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted or not reader.pages:
            raise ValueError("Encrypted or empty PDF")
        # Strict parsing resolves the complete page tree, including the last page.
        for page in reader.pages:
            page.get("/MediaBox")
        front = reader.pages[0].extract_text() or ""
        metadata = reader.metadata or {}
    except Exception:
        return result("CORRUPTED", "Strict PDF parsing failed")
    checks["pdf_structure"] = True
    digest = hashlib.sha256(content).hexdigest()
    anchor.update(sha256=digest, pages=len(reader.pages))
    if not isinstance(candidate, dict) or not isinstance(evidence, dict):
        return result("AMBIGUOUS", "Candidate and source evidence are required")
    if not re.fullmatch(r"[a-f0-9]{64}", str(evidence.get("sha256", ""))):
        return result("AMBIGUOUS", "Source evidence lacks a SHA-256 binding")
    checks["artifact_hash"] = digest == evidence["sha256"]
    if not checks["artifact_hash"]:
        return result("WRONG", "PDF bytes disagree with the acquisition hash")
    title, authors, year = candidate.get("title"), candidate.get("authors"), candidate.get("year")
    if (not isinstance(title, str) or not title.strip() or not isinstance(authors, list) or
            not authors or not all(isinstance(author, str) and author.strip() for author in authors) or
            isinstance(year, bool) or not re.fullmatch(r"\d{4}", str(year))):
        return result("AMBIGUOUS", "Acquired-version title, authors and year are required")
    html = evidence.get("html")
    if not isinstance(html, str) or not html.strip() or len(html) > 1_000_000:
        return result("AMBIGUOUS", "Captured official HTML is missing or outside the bounded limit")
    checks["capture_timestamp"] = _timestamp(evidence.get("retrieved_at"))
    if not checks["capture_timestamp"]:
        return result("AMBIGUOUS", "Source capture requires a timezone-aware retrieval timestamp")
    source, pdf_url = evidence.get("source_url"), evidence.get("pdf_url")
    try:
        kind = _source_kind(source)
        checks["official_pdf_destination"] = _pdf_destination(kind, source, pdf_url)
    except (ValueError, TypeError):
        return result("AMBIGUOUS", "Unsupported or invalid official source URL")
    if not checks["official_pdf_destination"]:
        return result("WRONG", "Acquired PDF URL belongs to another official paper identity")
    acquisition_url = evidence.get("acquisition_url", pdf_url)
    if acquisition_url != pdf_url:
        # Alternate public GitHub transport must serve the exact PMLR-linked
        # repository blob. Similar filenames or paths do not establish identity.
        raw_host, raw_path = _url(pdf_url)
        match = re.fullmatch(r"/mlresearch/(v\d+)/main/(assets/[\w-]+/[\w-]+\.pdf)", raw_path)
        repository = evidence.get("repository_file")
        if kind != "pmlr" or raw_host != "raw.githubusercontent.com" or not match or not isinstance(repository, dict):
            return result("AMBIGUOUS", "Alternate acquisition requires an exact official repository file binding")
        volume, asset = match.groups()
        expected_api = f"https://api.github.com/repos/mlresearch/{volume}/contents/{asset}?ref=main"
        blob = hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content, usedforsecurity=False).hexdigest()
        checks["repository_route"] = acquisition_url == expected_api and evidence.get("repository_metadata_url") == expected_api
        checks["repository_capture"] = _timestamp(evidence.get("repository_retrieved_at"))
        checks["repository_blob"] = repository.get("sha") == blob and repository.get("size") == len(content)
        checks["repository_path"] = repository.get("path") == asset and repository.get("download_url") == pdf_url and repository.get("type") == "file"
        if not all(checks[k] for k in ("repository_route", "repository_capture", "repository_blob", "repository_path")):
            return result("WRONG", "Alternate acquisition does not match the official repository blob")
        anchor.update(acquisition_url=acquisition_url, repository_blob_sha1=blob, repository_metadata_url=expected_api)
    parser = _CitationHTML()
    try:
        parser.feed(html)
    except Exception:
        return result("AMBIGUOUS", "Captured official HTML cannot be parsed")
    meta = parser.meta
    anchor.update(landing_url=source, pdf_url=pdf_url, retrieved_at=evidence["retrieved_at"],
                  html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest())
    if evidence.get("html_sha256") and evidence["html_sha256"] != anchor["html_sha256"]:
        return result("WRONG", "Captured HTML disagrees with its recorded digest")
    source_title = _one(meta, "citation_title")
    if source_title is None:
        return result("AMBIGUOUS", "Official citation title is missing or conflicting")
    checks["source_title"] = _compact(source_title) == _compact(title)
    if not checks["source_title"]:
        return result("WRONG", "Official source title disagrees with the candidate")
    source_authors = meta.get("citation_author", [])
    if not source_authors:
        return result("AMBIGUOUS", "Official citation authors are absent")
    checks["source_all_authors"] = [_author(author) for author in source_authors] == [_author(author) for author in authors]
    if not checks["source_all_authors"]:
        return result("WRONG", "Official acquired-version author list disagrees with the candidate")
    date_key = "citation_online_date" if kind == "arxiv" else "citation_publication_date"
    date = _one(meta, date_key)
    if not date or not re.fullmatch(r"\d{4}(?:[-/]\d{2}(?:[-/]\d{2})?)?", date):
        return result("AMBIGUOUS", "Official version publication date is missing or conflicting")
    checks["source_year"] = int(date[:4]) == int(year)
    if not checks["source_year"]:
        return result("WRONG", "Official version year disagrees; conference and publication dates must stay separate")
    anchor.update(title=source_title, authors=source_authors, publication_date=date)
    linked_pdf = _one(meta, "citation_pdf_url")
    if not linked_pdf:
        return result("AMBIGUOUS", "Official citation PDF link is missing or conflicting")
    version = evidence.get("version")
    expected_version = candidate.get("expected_version")
    if expected_version and expected_version != version:
        return result("AMBIGUOUS", "Acquired and expected version labels disagree")
    doi = candidate.get("doi")
    if doi and not _doi_value(doi):
        return result("AMBIGUOUS", "Candidate DOI is invalid")
    source_doi = _one(meta, "citation_doi")
    if len(set(meta.get("citation_doi", []))) > 1:
        return result("AMBIGUOUS", "Official source declares conflicting DOI identities")
    if source_doi and not _doi_value(source_doi):
        return result("AMBIGUOUS", "Official source DOI is invalid")
    if kind != "arxiv" and doi:
        if not source_doi:
            return result("AMBIGUOUS", "Official publication does not substantiate the supplied DOI")
        checks["source_doi"] = _doi_value(doi) == _doi_value(source_doi)
        if not checks["source_doi"]:
            return result("WRONG", "Official publication DOI disagrees with the candidate")
    if source_doi:
        anchor["doi"] = _doi_value(source_doi)
    main_heading = re.split(r"(?im)^\s*abstract\s*:?\s*$", front, maxsplit=1)[0]
    if re.search(r"(?im)^\s*(?:supplement(?:ary|al)?(?:\s+(?:material|information))?|supporting information|appendix only)\b", main_heading[:1800]):
        return result("SUPPLEMENT", "PDF heading marks a supplement, not the main paper")
    checks["main_document"] = True
    checks["pdf_title"] = _heading_matches(front, title)
    if not checks["pdf_title"]:
        return result("WRONG", "PDF heading disagrees with the official candidate title")
    author_region = _compact(main_heading[:3000] + " " + str(metadata.get("/Author", "")))
    variants = evidence.get("author_name_variants", [])
    if not isinstance(variants, list):
        return result("AMBIGUOUS", "Author name variants require an explicit evidence list")
    mapped, observed_variants = {}, []
    for variant in variants:
        if not isinstance(variant, dict):
            return result("AMBIGUOUS", "Invalid explicit author name variant")
        source_name, pdf_name = variant.get("source_name"), variant.get("pdf_name")
        source_tokens, pdf_tokens = _name_tokens(source_name), _name_tokens(pdf_name)
        identity = _author(source_name)
        if (variant.get("kind") != "additional_middle_names" or type(variant.get("page")) is not int or variant["page"] != 1
                or len(source_tokens) != 2 or not 3 <= len(pdf_tokens) <= 5
                or source_tokens[0] != pdf_tokens[0] or source_tokens[-1] != pdf_tokens[-1]
                or sum(_author(author) == identity for author in source_authors) != 1
                or identity in mapped or _author(pdf_name) in mapped.values()
                or _author(pdf_name) not in _compact(main_heading[:3000])):
            return result("AMBIGUOUS", "Declared author variant is not a unique, printed additional-middle-name form")
        mapped[identity] = _author(pdf_name)
        observed_variants.append(dict(variant))
    checks["pdf_all_authors"] = all(
        _author(author) in author_region or mapped.get(_author(author), "\0") in _compact(main_heading[:3000])
        for author in authors
    )
    if not checks["pdf_all_authors"]:
        return result("WRONG", "PDF lacks one or more acquired-version authors")
    if observed_variants:
        anchor["author_name_variants"] = observed_variants
    primary_dois = {_doi_value(value.rstrip(".,;)")) for value in re.findall(r"10\.\d{4,9}/[^\s<>\"]+", main_heading[:1800])}
    primary_dois.discard(None)
    declared_doi = _doi_value(metadata.get("/doi"))
    if declared_doi:
        primary_dois.add(declared_doi)
    if len(primary_dois) > 1:
        return result("AMBIGUOUS", "PDF primary identity declares multiple DOIs")
    expected_doi = doi or source_doi
    if primary_dois and expected_doi and primary_dois != {_doi_value(expected_doi)}:
        return result("WRONG", "PDF primary DOI disagrees with the selected identity")
    plain_front = " ".join(front.split())
    if kind == "arxiv":
        arxiv = candidate.get("arxiv_id_version", candidate.get("arxiv"))
        if not isinstance(arxiv, str) or not re.fullmatch(r"\d{4}\.\d{4,5}v[1-9]\d*", arxiv):
            return result("AMBIGUOUS", "Exact selected arXiv version is required")
        base = arxiv.rsplit("v", 1)[0]
        checks["exact_version_source"] = source == "https://arxiv.org/abs/" + arxiv and pdf_url.removesuffix(".pdf") == "https://arxiv.org/pdf/" + arxiv
        checks["source_arxiv_identity"] = _one(meta, "citation_arxiv_id") in {base, arxiv}
        checks["source_pdf_link"] = linked_pdf.removesuffix(".pdf") in {"https://arxiv.org/pdf/" + base, "https://arxiv.org/pdf/" + arxiv}
        observed = set(re.findall(r"arXiv:\s*(\d{4}\.\d{4,5}v[1-9]\d*)", front))
        if not observed:
            return result("AMBIGUOUS", "PDF has no exact arXiv version watermark")
        checks["pdf_arxiv_version"] = observed == {arxiv}
        checks["version"] = version == "arxiv:" + arxiv
        if not all(checks[key] for key in ("exact_version_source", "source_arxiv_identity", "source_pdf_link", "pdf_arxiv_version", "version")):
            return result("WRONG", "arXiv landing, PDF link or embedded version disagrees with the selected version")
        if doi:
            checks["source_doi"] = _doi_value(doi) == _doi_value("10.48550/arXiv." + base)
            if not checks["source_doi"]:
                return result("WRONG", "arXiv bytes cannot substantiate another publication DOI")
        anchor["arxiv_id_version"] = arxiv
    else:
        checks["source_pdf_link"] = linked_pdf == pdf_url
        if not checks["source_pdf_link"]:
            return result("WRONG", "Official main-paper PDF link differs from the acquired URL")
        if kind in {"neurips", "iclr"}:
            source_year = int(re.search(r"/paper/(\d{4})/", source).group(1))
            pattern = r"Conference on Neural Information Processing Systems\s*\(NeurIPS\s+(\d{4})\)" if kind == "neurips" else r"Published as a conference paper at ICLR\s+(\d{4})"
            imprint = re.search(pattern, plain_front, re.I)
            checks["pdf_publication_imprint"] = bool(imprint) and int(imprint.group(1)) == source_year
            conference_year = candidate.get("conference_year", source_year)
            checks["conference_year"] = bool(re.fullmatch(r"\d{4}", str(conference_year))) and int(conference_year) == source_year
        elif kind == "pmlr":
            volume = re.search(r"/v(\d+)/", source).group(1)
            pattern = r"Proceedings of the .*?International Conference on Machine Learning.*?PMLR\s+(\d+),\s+(\d{4})"
            imprint = re.search(pattern, plain_front, re.I)
            checks["pdf_publication_imprint"] = bool(imprint) and imprint.group(1) == volume and int(imprint.group(2)) == int(year)
        else:
            if version != "acceptedVersion":
                return result("AMBIGUOUS", "CVF OA accepted copy must not be labelled the final published version")
            policy = evidence.get("policy_html")
            try:
                policy_host, policy_path = _url(evidence.get("policy_url"))
            except (ValueError, TypeError):
                return result("AMBIGUOUS", "Captured official CVF accepted-version policy is required")
            edition = re.search(r"/content/(CVPR\d{4})/", source).group(1)
            checks["cvf_policy_source"] = policy_host == "openaccess.thecvf.com" and policy_path.rstrip("/") == "/" + edition
            checks["cvf_policy_timestamp"] = _timestamp(evidence.get("policy_retrieved_at"))
            if not isinstance(policy, str) or not policy.strip() or len(policy) > 1_000_000:
                return result("AMBIGUOUS", "Captured CVF policy HTML is missing")
            policy_parser = _CitationHTML(); policy_parser.feed(policy)
            plain_policy = " ".join(" ".join(policy_parser.text).split())
            accepted = r"identical to the accepted version(?:s)?"
            final = r"final published version.*?IEEE Xplore"
            checks["cvf_policy_version"] = bool(re.search(accepted, plain_policy, re.I) and re.search(final, plain_policy, re.I))
            checks["pdf_publication_imprint"] = "Open Access version, provided by the Computer Vision Foundation".casefold() in plain_front.casefold() and bool(re.search(accepted, plain_front, re.I) and re.search(final, plain_front, re.I))
            if not all(checks[key] for key in ("cvf_policy_source", "cvf_policy_timestamp", "cvf_policy_version")):
                return result("AMBIGUOUS", "CVF policy does not substantiate the accepted-version classification")
            anchor.update(policy_url=evidence["policy_url"], policy_html_sha256=hashlib.sha256(policy.encode("utf-8")).hexdigest())
        if not checks["pdf_publication_imprint"]:
            return result("AMBIGUOUS", "PDF lacks the required publication or accepted-copy imprint")
        if checks.get("conference_year") is False:
            return result("WRONG", "Conference year disagrees with the official source and PDF imprint")
        if kind != "cvf" and version != "publishedVersion":
            return result("AMBIGUOUS", "Official proceedings bytes require a distinct publishedVersion identity")
        if re.search(r"(?im)^\s*(?:preprint|submitted manuscript|not peer reviewed|author accepted manuscript)\b", main_heading):
            return result("AMBIGUOUS", "PDF version label conflicts with the official publication identity")
        checks["version"] = True
    anchor["version"] = version
    return result("VERIFIED", "Official source identity, complete author list, main PDF link, artifact hash and embedded version evidence agree",
                  observed_version=version, identity_scope="bibliographic/version identity; agent verification, not human scientific review")
