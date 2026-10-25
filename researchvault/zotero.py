"""Zotero Local API reads and deliberately create-only writes.

No database access, replacement, deletion, authorization dialog or automatic retry.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import url2pathname
import uuid

from .acquisition import verify_pdf
from .discovery import Response, normalize_doi, now
from .identity import arxiv as normalize_arxiv
from .safety import read_only_mode

MANUAL = "MANUAL_RECONCILIATION_REQUIRED"


def local_request(method, url, *, headers=None, body=None, max_bytes=4_000_000):
    p = urlsplit(url)
    if p.scheme != "http" or p.hostname not in {"localhost", "127.0.0.1"} or p.port != 23119 or not p.path.startswith("/api/") or p.username or p.password:
        raise ValueError("Only the explicit Zotero loopback Local API is supported")
    connection = http.client.HTTPConnection("127.0.0.1", 23119, timeout=30)
    try:
        connection.request(method, p.path + ("?" + p.query if p.query else ""), body=body, headers=headers or {})
        result = connection.getresponse()
        content = result.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError("Zotero response exceeds the byte limit")
        return Response(result.status, dict(result.getheaders()), content)
    finally:
        connection.close()


def _key(key):
    if not re.fullmatch(r"[A-Z0-9]{8}", str(key)):
        raise ValueError("Invalid Zotero item key")
    return key


def _data(item):
    return item.get("data", item)


def _doi(item):
    try:
        return normalize_doi(_data(item).get("DOI"))
    except ValueError:
        return None


def _publisher_id(item):
    """Only explicit publisher paper routes can provide DOI-less identities."""
    p = urlsplit(str(_data(item).get("url", "")))
    if p.scheme != "https" or p.query or p.fragment:
        return None
    if p.netloc == "proceedings.mlr.press":
        match = re.fullmatch(r"/v([0-9]+)/([A-Za-z0-9_-]+)\.html", p.path)
        return ("pmlr", *match.groups()) if match else None
    if p.netloc in {"proceedings.neurips.cc", "proceedings.iclr.cc"}:
        match = re.fullmatch(r"/paper_files/paper/([0-9]{4})/hash/([a-f0-9]{32})-Abstract-[A-Za-z_]+\.html", p.path)
        return (p.netloc, *match.groups()) if match else None
    if p.netloc == "openaccess.thecvf.com":
        match = re.fullmatch(r"/content/([A-Z0-9]+)/html/([A-Za-z0-9_-]+)_paper\.html", p.path)
        return ("cvf", *match.groups()) if match else None
    return None


def publication_identity(item):
    """Return a stable bibliographic identity from metadata or a Zotero envelope.

    DOI fields accept ``DOI`` or candidate ``doi``. Exact arXiv versions may be
    supplied in ``arxiv_id_version``, ``arxiv_id``, ``arxiv``, ``archiveID``, a
    canonical HTTPS arxiv.org/abs URL (``url`` or ``source_url``), or an explicit
    ``arXiv: ID`` / ``arXiv ID: ID`` Extra line. An unversioned arXiv reference
    retains its base but has no canonical_id. Contradictory arXiv declarations
    raise ValueError. A journal DOI or publisher identity stays distinct from a
    related arXiv reference; titles never contribute identity.
    """
    data = _data(item)
    raw_dois = [data.get(name) for name in ("DOI", "doi") if data.get(name)]
    dois = {normalize_doi(value) for value in raw_dois}
    if len(dois) > 1:
        raise ValueError("Conflicting DOI declarations")
    doi = next(iter(dois), None)
    declarations = []
    for name in ("arxiv_id_version", "arxiv_id", "arxiv"):
        if data.get(name):
            declarations.append(normalize_arxiv(data[name]))
    archive_id = data.get("archiveID")
    if archive_id:
        try:
            declarations.append(normalize_arxiv(archive_id))
        except ValueError:
            if str(data.get("archive", "")).casefold() == "arxiv":
                raise ValueError("Invalid arXiv archiveID") from None
    for field in ("url", "source_url"):
        p = urlsplit(str(data.get(field, "")))
        if p.scheme == "https" and p.netloc == "arxiv.org" and not p.query and not p.fragment and p.path.startswith("/abs/"):
            declarations.append(normalize_arxiv(p.path.removeprefix("/abs/")))
    for line in str(data.get("extra", "")).splitlines():
        match = re.fullmatch(r"\s*(?:arxiv(?:\s+id)?|arxiv_id(?:_version)?)\s*:\s*(.*?)\s*", line, re.I)
        if match:
            value = re.sub(r"\s+\[[A-Za-z0-9.-]+\]\s*$", "", match.group(1))
            declarations.append(normalize_arxiv(value))
    arxiv_doi = bool(doi and doi.startswith("10.48550/arxiv."))
    if arxiv_doi:
        declarations.append(normalize_arxiv(doi.removeprefix("10.48550/arxiv.")))
    declarations = [value.casefold() for value in declarations if value]
    bases = {re.sub(r"v[1-9]\d*$", "", value) for value in declarations}
    exact = {value for value in declarations if re.search(r"v[1-9]\d*$", value)}
    if len(bases) > 1 or len(exact) > 1:
        raise ValueError("Conflicting arXiv publication or version declarations")
    base, version = next(iter(bases), None), next(iter(exact), None)
    publisher = _publisher_id(data)
    canonical = ("doi:" + doi if doi and not arxiv_doi else
                 "publisher:" + ":".join(publisher) if publisher else
                 "arxiv:" + version if version else None)
    return {"doi": doi, "publisher_id": publisher, "arxiv_id": base,
            "arxiv_id_version": version, "canonical_id": canonical}


def publication_match(expected, existing):
    """Return EXACT, AMBIGUOUS or DISTINCT without title or version inference.

    Inputs use the same metadata/envelope form as publication_identity. Related
    journal and arXiv records remain distinct. A shared arXiv base with an unknown
    version requires reconciliation; two explicitly different versions do not.
    """
    left, right = publication_identity(expected), publication_identity(existing)
    left_arxiv = bool(left["arxiv_id"] and (left["canonical_id"] is None or left["canonical_id"].startswith("arxiv:")))
    right_arxiv = bool(right["arxiv_id"] and (right["canonical_id"] is None or right["canonical_id"].startswith("arxiv:")))
    if left_arxiv or right_arxiv:
        if left_arxiv and right_arxiv and left["arxiv_id"] == right["arxiv_id"]:
            if not left["arxiv_id_version"] or not right["arxiv_id_version"]:
                return "AMBIGUOUS"
            return "EXACT" if left["arxiv_id_version"] == right["arxiv_id_version"] else "DISTINCT"
        return "DISTINCT"
    same_doi = bool(left["doi"] and left["doi"] == right["doi"])
    same_publisher = bool(left["publisher_id"] and left["publisher_id"] == right["publisher_id"])
    if same_publisher and left["doi"] and right["doi"] and not same_doi:
        return "AMBIGUOUS"
    if same_doi and left["publisher_id"] and right["publisher_id"] and not same_publisher:
        return "AMBIGUOUS"
    return "EXACT" if same_doi or same_publisher else "DISTINCT"


class _Receipt:
    def __init__(self, path, intent, callback=None):
        self.path, self.callback = Path(path), callback
        if self.path.is_symlink():
            raise ValueError("Receipt cannot be a symbolic link")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps({"status": "INTENT", **intent}, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            raise ValueError(MANUAL + ": a durable receipt already exists; inspect it before proceeding") from None

    def event(self, status, **details):
        value = {"status": status, "at": now(), **details}
        if self.path.is_symlink():
            raise ValueError("Receipt cannot be a symbolic link")
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if self.callback and status == "MUTATION_INTENT":
            self.callback(value)


class Client:
    def __init__(self, library, *, base_url="http://127.0.0.1:23119/api", transport=None, api_key_env="ZOTERO_API_KEY", read_only=False):
        self.read_only = read_only_mode(read_only)
        library = re.sub(r"^user:", "users/", str(library))
        library = re.sub(r"^group:", "groups/", library)
        if not re.fullmatch(r"(?:users|groups)/\d+", library):
            raise ValueError("A users/<id> or groups/<id> library namespace is required")
        p = urlsplit(base_url)
        if p.scheme != "http" or p.hostname not in {"localhost", "127.0.0.1"} or p.port != 23119 or p.path.rstrip("/") != "/api" or p.query or p.fragment or p.username or p.password:
            raise ValueError("Unsupported Zotero Local API origin")
        self.library = library
        self.base_url = base_url.rstrip("/")
        self.transport = transport or local_request
        self.api_key_env = api_key_env
        self.server_id = None
        self.library_version = None

    def _url(self, suffix):
        return self.base_url + "/" + self.library + suffix

    def _request(self, method, url, *, body=None, headers=None, mutation=False, upload=False):
        if method != 'GET' or mutation or upload:
            self._require_writable()
        if method not in {"GET", "POST"}:
            raise ValueError("Only reads and create-only POST operations are allowed")
        p, origin = urlsplit(url), urlsplit(self.base_url)
        if (p.scheme, p.netloc) != (origin.scheme, origin.netloc) or not p.path.startswith("/api/") or p.fragment or p.username or p.password:
            raise ValueError("Zotero request escaped its configured API origin")
        request_headers = {"Zotero-API-Version": "3", **(headers or {})}
        if self.server_id and not upload:
            request_headers["Zotero-Server-ID"] = self.server_id
        if mutation and not upload:
            key = os.environ.get(self.api_key_env)
            if not key or not self.server_id:
                raise ValueError("Writes require an environment API key and a Zotero 10+ Server ID")
            request_headers["Zotero-API-Key"] = key
        result = self.transport(method, url, headers=request_headers, body=body, max_bytes=8_000_000)
        if len(result.body) > 8_000_000:
            raise ValueError("Zotero response exceeds byte limit")
        server = result.header("Zotero-Server-ID")
        if not 200 <= result.status < 300:
            raise ValueError(f"Zotero API returned HTTP {result.status}")
        # The upload key authorizes the byte-upload endpoint, whose response
        # need not include the normal API Server ID. Other responses must.
        if self.server_id and (server != self.server_id if not upload else server and server != self.server_id):
            raise ValueError("Zotero Server ID changed or disappeared")
        if server:
            self.server_id = server
        return result

    def _get(self, url):
        result = self._request("GET", url)
        return json.loads(result.body), result

    def _validate_namespace(self, item):
        library = item.get("library")
        if library:
            kind, ident = self.library.split("/")
            if library.get("type") != ("user" if kind == "users" else "group"):
                raise ValueError("Zotero response belongs to another library type")
            if ident != "0" and str(library.get("id")) != ident:
                raise ValueError("Zotero response belongs to another library")

    def inventory(self):
        """Read every page, including attachments; reject unstable or partial inventories."""
        items, seen, start, version, total = [], set(), 0, None, None
        for _ in range(10000):
            url = self._url("/items?") + urlencode({"format": "json", "limit": 100, "start": start, "sort": "dateAdded", "direction": "asc"})
            page, response = self._get(url)
            if not isinstance(page, list):
                raise ValueError("Expected an item-list response")
            current = response.header("Last-Modified-Version")
            if not current:
                raise ValueError("Cannot certify a complete inventory without library version")
            if version is not None and current != version:
                raise ValueError("Library changed during paged inventory; retry read-only inventory")
            version = current
            reported = response.header("Total-Results")
            if reported:
                if total is not None and int(reported) != total:
                    raise ValueError("Inventory total changed during pagination")
                total = int(reported)
            for item in page:
                self._validate_namespace(item)
                key = _key(item.get("key") or _data(item).get("key"))
                if key in seen:
                    raise ValueError("Duplicate page/key indicates incomplete inventory")
                seen.add(key)
                items.append(item)
            start += len(page)
            if total is not None:
                if start > total or (not page and start < total):
                    raise ValueError("Inventory count is inconsistent")
                if start == total:
                    break
            elif not page or (len(page) < 100 and 'rel="next"' not in response.header("Link")):
                break
        else:
            raise ValueError("Inventory page limit reached; no writes permitted")
        self.library_version = version
        return {"library": self.library, "server_id": self.server_id,
                "version": version, "complete": True, "items": items}

    def find_pdf(self, *, zotero_key=None, pdf_key=None, doi=None):
        inventory = self.inventory()
        items = inventory["items"]
        parents = [i for i in items if _data(i).get("itemType") not in {"attachment", "annotation", "note"}]
        if zotero_key is not None:
            matches = [i for i in parents if i.get("key") == _key(zotero_key)]
            if not matches:
                raise ValueError("Explicit parent key not found; no fallback matching")
            if doi and _doi(matches[0]) != normalize_doi(doi):
                raise ValueError("Explicit key and DOI disagree")
        elif doi:
            matches = [i for i in parents if _doi(i) == normalize_doi(doi)]
        else:
            raise ValueError("An explicit parent key or DOI is required")
        if len(matches) != 1:
            return {"status": "AMBIGUOUS" if matches else "MISSING", "library": self.library, "parents": matches}
        parent = matches[0]
        attachments = [i for i in items if _data(i).get("parentItem") == parent["key"] and _data(i).get("itemType") == "attachment" and _data(i).get("contentType") == "application/pdf"]
        if pdf_key is not None:
            attachments = [i for i in attachments if i.get("key") == _key(pdf_key)]
            if not attachments:
                raise ValueError("Explicit PDF key is not attached to the selected parent")
        return {"status": "FOUND" if len(attachments) == 1 else "AMBIGUOUS" if attachments else "MISSING",
                "library": self.library, "server_id": self.server_id, "parent": parent, "attachments": attachments}

    def read_pdf(self, pdf_key, *, parent_key=None, max_bytes=50_000_000):
        """Read an exact inventoried attachment via the Local API's file URI.

        The endpoint /items/<key>/file/view/url supplies a plain-text local URI.
        No storage/database inference, remote shares, linked HTTP downloads or
        mutations are permitted. The bytes must match the inventoried PDF MD5.
        """
        pdf_key = _key(pdf_key)
        if parent_key is not None:
            parent_key = _key(parent_key)
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("PDF byte limit must be a positive integer")
        inventory = self.inventory()
        if not inventory.get("server_id"):
            raise ValueError("PDF reads require an identified Zotero server")
        selected = [item for item in inventory["items"] if item.get("key") == pdf_key]
        if len(selected) != 1:
            raise ValueError("Exact PDF attachment not found in this library")
        attachment = _data(selected[0])
        if (attachment.get("key", pdf_key) != pdf_key or attachment.get("itemType") != "attachment"
                or attachment.get("contentType") != "application/pdf"):
            raise ValueError("Selected item is not the exact PDF attachment")
        actual_parent = _key(attachment.get("parentItem"))
        if parent_key is not None and parent_key != actual_parent:
            raise ValueError("PDF attachment belongs to another parent")
        parents = [item for item in inventory["items"] if item.get("key") == actual_parent
                   and _data(item).get("itemType") not in {"attachment", "annotation", "note"}]
        if len(parents) != 1 or _data(parents[0]).get("key", actual_parent) != actual_parent:
            raise ValueError("PDF attachment has no exact bibliographic parent")
        expected_md5 = attachment.get("md5")
        if not isinstance(expected_md5, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", expected_md5):
            raise ValueError("PDF attachment lacks a valid content MD5")
        response = self._request("GET", self._url("/items/" + pdf_key + "/file/view/url"))
        if response.status != 200 or response.header("Content-Type").split(";", 1)[0].strip().lower() != "text/plain":
            raise ValueError("PDF file-URI endpoint must return HTTP 200 plain text")
        try:
            value = response.body.decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            raise ValueError("PDF file URI is not UTF-8 text") from None
        uri = urlsplit(value)
        if (not value.lower().startswith("file:///") or uri.scheme != "file" or uri.netloc or "?" in value or "#" in value
                or any(ord(char) < 33 for char in value)):
            raise ValueError("PDF requires a local file URI without a host, query or fragment")
        native = url2pathname(uri.path)
        def local_absolute(value):
            text = str(value)
            return (Path(value).is_absolute() and not text.startswith(("\\\\", "//"))
                    and not PureWindowsPath(text).drive.startswith("\\\\"))
        if not local_absolute(native):
            raise ValueError("PDF file URI must resolve to a local absolute path, never a share")
        path = Path(native).resolve(strict=True)
        if not local_absolute(path) or not path.is_file():
            raise ValueError("PDF path is not a local regular file")
        if path.stat().st_size > max_bytes:
            raise ValueError("PDF exceeds the byte limit")
        with path.open("rb") as stream:
            content = stream.read(max_bytes + 1)
        if len(content) > max_bytes or not content.startswith(b"%PDF-"):
            raise ValueError("PDF signature or size invalid")
        actual_md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
        if actual_md5 != expected_md5.lower():
            raise ValueError("PDF bytes disagree with the attachment MD5")
        return {"path": str(path), "content": content, "sha256": hashlib.sha256(content).hexdigest(),
                "md5": actual_md5, "pdf_key": pdf_key, "zotero_key": actual_parent,
                "library": self.library, "server_id": self.server_id}

    def _receipt(self, path, operation, payload, persist):
        self._require_writable()
        if path is None:
            raise ValueError("Writes require an explicit durable receipt path outside the Vault")
        if not os.environ.get(self.api_key_env) or not self.server_id:
            raise ValueError("Writes require an environment API key and Zotero 10+ Server ID")
        intent = {"operation": operation, "library": self.library, "server_id": self.server_id,
                  "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), "at": now()}
        return _Receipt(path, intent, persist)

    def _mutate(self, receipt, step, url, body, headers, *, upload=False):
        self._require_writable()
        receipt.event("MUTATION_INTENT", step=step)
        return self._request("POST", url, body=body, headers=headers, mutation=True, upload=upload)

    def _create(self, item, receipt):
        if any(field in item for field in ("key", "version", "data")):
            raise ValueError("Create operation cannot contain an existing Zotero identity")
        response = self._mutate(receipt, "create_item", self._url("/items"), json.dumps([item]).encode(),
                                {"Content-Type": "application/json", "Zotero-Write-Token": uuid.uuid4().hex,
                                 "If-Unmodified-Since-Version": self.library_version})
        result = json.loads(response.body)
        if result.get("failed") or result.get("unchanged"):
            raise ValueError("Create operation was rejected or returned an unexpected unchanged item")
        saved = result.get("successful", {}).get("0")
        key = (saved.get("key") if isinstance(saved, dict) else None) or result.get("success", {}).get("0")
        key = _key(key)
        readback, _ = self._get(self._url("/items/" + key))
        self._validate_namespace(readback)
        data = _data(readback)
        if readback.get("key") != key or any(data.get(k) != item.get(k) for k in ("itemType", "title", "parentItem", "linkMode", "creators", "date", "url") if k in item):
            raise ValueError("New item readback did not match the mutation intent")
        if item.get("DOI") and _doi(readback) != normalize_doi(item["DOI"]):
            raise ValueError("New item DOI readback mismatch")
        if not item.get("DOI") and _publisher_id(item) and _publisher_id(readback) != _publisher_id(item):
            raise ValueError("New item publisher identity readback mismatch")
        intended = publication_identity(item)
        if intended["canonical_id"] and intended["canonical_id"].startswith("arxiv:") and publication_match(item, readback) != "EXACT":
            raise ValueError("New item arXiv version identity readback mismatch")
        receipt.event("ITEM_READBACK", key=key)
        return readback

    def create_item(self, item, *, apply=False, receipt_path=None, persist=None):
        if apply:
            self._require_writable()
        if apply and receipt_path and Path(receipt_path).exists():
            return {"status": MANUAL, "receipt": str(receipt_path)}
        if any(k in item for k in ("key", "version", "data", "parentItem")) or item.get("itemType") in {"attachment", "annotation", "note"}:
            raise ValueError("Only new bibliographic parent items are accepted")
        identity = publication_identity(item)
        if not identity["canonical_id"]:
            raise ValueError("Creation requires DOI, a canonical publisher paper identity or an exact arXiv version")
        if not item.get("title") or not item.get("creators") or not item.get("date"):
            raise ValueError("Creation requires title, creators and date")
        inventory = self.inventory()
        parents = [i for i in inventory["items"] if _data(i).get("itemType") not in {"attachment", "annotation", "note"}]
        matches, uncertain = [], []
        for parent in parents:
            outcome = publication_match(item, parent)
            if outcome == "EXACT":
                matches.append(parent)
            elif outcome == "AMBIGUOUS":
                uncertain.append(parent)
        if uncertain:
            return {"status": "AMBIGUOUS", "reason": "Publication identity or arXiv version requires reconciliation", "items": matches + uncertain}
        if matches:
            return {"status": "EXISTS" if len(matches) == 1 else "AMBIGUOUS", "library": self.library, "items": matches}
        title = re.sub(r"\W+", "", item["title"]).casefold()
        def distinct_arxiv_version(other):
            found = publication_identity(other)
            return (identity["canonical_id"].startswith("arxiv:")
                    and str(found["canonical_id"]).startswith("arxiv:")
                    and identity["arxiv_id"] == found["arxiv_id"]
                    and identity["arxiv_id_version"] != found["arxiv_id_version"])
        if any(re.sub(r"\W+", "", str(_data(i).get("title", ""))).casefold() == title and not distinct_arxiv_version(i)
               for i in parents):
            return {"status": "AMBIGUOUS", "reason": "Title resemblance requires version/identity review"}
        if not apply:
            return {"status": "PLANNED", "library": self.library, "item": item}
        # /items/new is a Web API convenience, absent from the Local API.
        # Editable creation JSON only requires these container fields and
        # itemType; Zotero validates the supplied item-specific fields.
        payload = {"tags": [], "collections": [], "relations": {}, **item}
        receipt = self._receipt(receipt_path, "create_parent", payload, persist)
        try:
            saved = self._create(payload, receipt)
            receipt.event("COMPLETE", key=saved["key"])
            return {"status": "CREATED", "library": self.library, "server_id": self.server_id, "item": saved}
        except Exception as exc:
            receipt.event(MANUAL, error_type=type(exc).__name__)
            return {"status": MANUAL, "receipt": str(receipt_path)}

    def import_pdf(self, parent_key, pdf_path, candidate, *, apply=False, receipt_path=None, persist=None, verifier=None):
        if apply:
            self._require_writable()
        if apply and receipt_path and Path(receipt_path).exists():
            return {"status": MANUAL, "receipt": str(receipt_path)}
        parent_key = _key(parent_key)
        content = Path(pdf_path).read_bytes()
        if len(content) > 50_000_000 or not content.startswith(b"%PDF-"):
            raise ValueError("PDF signature or size invalid")
        verdict = (verifier or verify_pdf)(content, candidate)
        if verdict.get("status") != "VERIFIED":
            raise ValueError("Only a verified main PDF can be imported")
        existing = self.find_pdf(zotero_key=parent_key)
        if publication_match(candidate, existing["parent"]) != "EXACT":
            raise ValueError("Existing parent publication/version identity conflicts with selected metadata")
        normalize_title = lambda value: re.sub(r"\W+", "", str(value)).casefold()
        if normalize_title(_data(existing["parent"]).get("title")) != normalize_title(candidate["title"]):
            raise ValueError("Existing parent title conflicts with selected canonical metadata")
        if existing.get("attachments"):
            return {"status": "EXISTS", "library": self.library, "attachments": existing["attachments"]}
        filename = Path(pdf_path).name
        payload = {"itemType": "attachment", "linkMode": "imported_file", "parentItem": parent_key,
                   "title": candidate["title"], "contentType": "application/pdf", "filename": filename,
                   "tags": [], "collections": [], "relations": {}}
        if not apply:
            return {"status": "PLANNED", "library": self.library, "item": payload, "sha256": hashlib.sha256(content).hexdigest()}
        receipt = self._receipt(receipt_path, "create_pdf", {**payload, "sha256": hashlib.sha256(content).hexdigest()}, persist)
        try:
            saved = self._create(payload, receipt)
            key = saved["key"]
            endpoint = self._url("/items/" + key + "/file")
            file_hash = hashlib.md5(content, usedforsecurity=False).hexdigest()
            conditions = {"Content-Type": "application/x-www-form-urlencoded", "If-None-Match": "*"}
            form = {"md5": file_hash, "filename": filename, "filesize": len(content), "mtime": int(Path(pdf_path).stat().st_mtime * 1000)}
            authorization = self._mutate(receipt, "authorize_file", endpoint, urlencode(form).encode(), conditions)
            upload = json.loads(authorization.body)
            if not upload.get("exists"):
                expected = self.base_url + "/local/uploads/" + str(upload["uploadKey"])
                if upload.get("url") != expected or upload.get("prefix") or upload.get("suffix"):
                    raise ValueError("Unexpected local upload contract or target")
                response = self._mutate(receipt, "upload_file", expected, content, {"Content-Type": upload["contentType"]}, upload=True)
                if response.status != 201:
                    raise ValueError("File upload did not return 201")
                response = self._mutate(receipt, "register_file", endpoint, urlencode({"upload": upload["uploadKey"]}).encode(), conditions)
                if response.status != 204:
                    raise ValueError("File registration did not return 204")
            readback, _ = self._get(self._url("/items/" + key))
            data = _data(readback)
            if readback.get("key") != key or data.get("parentItem") != parent_key or data.get("md5") != file_hash or data.get("filename") != filename:
                raise ValueError("Registered file metadata readback mismatch")
            receipt.event("COMPLETE", zotero_key=parent_key, pdf_key=key, sha256=hashlib.sha256(content).hexdigest())
            return {"status": "CREATED", "library": self.library, "server_id": self.server_id, "zotero_key": parent_key, "pdf_key": key}
        except Exception as exc:
            receipt.event(MANUAL, error_type=type(exc).__name__)
            return {"status": MANUAL, "receipt": str(receipt_path)}

    def _require_writable(self):
        if read_only_mode(self.read_only):
            raise ValueError('Zotero mutation is blocked in read-only validation mode')
