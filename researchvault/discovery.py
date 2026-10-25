"""Bounded metadata discovery. Results are candidates, never scientific findings."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit

from . import __version__


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict
    body: bytes

    def header(self, name, default=""):
        return next((v for k, v in self.headers.items() if k.lower() == name.lower()), default)


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize_doi(value):
    value = str(value or "").strip()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.I)
    if not re.fullmatch(r"10\.\d{4,9}/[^\s\x00-\x1f]+", value):
        raise ValueError("A complete DOI is required")
    return value.lower()


def public_url(url):
    """Reject credentials, private destinations and session-bearing URLs before I/O."""
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.fragment:
        raise ValueError("Public downloads require credential-free HTTPS URLs")
    if p.port not in (None, 443) or any(ord(c) < 33 for c in url):
        raise ValueError("Unsupported URL port or control characters")
    secret = re.compile(r"(?:token|secret|password|signature|credential|session|cookie|api.?key|auth|saml)", re.I)
    if any(secret.search(k) for k, _ in parse_qsl(p.query)):
        raise ValueError("Session or secret URL parameters are prohibited")
    if p.hostname.lower() == "localhost" or p.hostname.lower().endswith((".localhost", ".local")):
        raise ValueError("Private network destination prohibited")
    try:
        address = ipaddress.ip_address(p.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Private network destination prohibited")
    return p


def public_request(method, url, *, headers=None, body=None, max_bytes=4_000_000):
    """One HTTPS request, pinned to validated DNS; no proxies, cookies or redirects."""
    p = public_url(url)
    if method != "GET" or body is not None:
        raise ValueError("The public metadata/download transport is read-only")
    if any(k.lower() in {"authorization", "cookie", "proxy-authorization"} for k in (headers or {})):
        raise ValueError("Public requests cannot carry credentials")
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("DNS resolved to a non-public address")
    address = addresses[0][4][0]
    connection = http.client.HTTPSConnection(p.hostname, timeout=20)
    # Connecting to the checked IP avoids a second DNS lookup; TLS authenticates the hostname.
    raw = socket.create_connection((address, 443), timeout=20)
    connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=p.hostname)
    deadline = time.monotonic() + 60
    try:
        connection.request(method, p.path + ("?" + p.query if p.query else ""), headers=headers or {})
        result = connection.getresponse()
        length = result.getheader("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError("Response exceeds byte limit")
        parts, count = [], 0
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("Response exceeded time limit")
            chunk = result.read(min(65536, max_bytes + 1 - count))
            count += len(chunk)
            if count > max_bytes:
                raise ValueError("Response exceeds byte limit")
            if not chunk:
                break
            parts.append(chunk)
        return Response(result.status, dict(result.getheaders()), b"".join(parts))
    finally:
        connection.close()


def get(url, *, transport=None, max_bytes=4_000_000, redirects=4):
    sender = transport or public_request
    for attempt in range(redirects + 1):
        public_url(url)
        response = sender("GET", url, headers={"User-Agent": f"ResearchVault/{__version__}", "Accept": "application/json, application/pdf"}, body=None, max_bytes=max_bytes)
        if len(response.body) > max_bytes:
            raise ValueError("Response exceeds byte limit")
        if response.status in {301, 302, 303, 307, 308}:
            if attempt == redirects or not response.header("Location"):
                raise ValueError("Redirect limit or missing location")
            url = urljoin(url, response.header("Location"))
            continue
        if response.status != 200:
            raise ValueError(f"HTTP request failed with status {response.status}")
        return response, url
    raise ValueError("Redirect limit")


def get_json(url, *, transport=None):
    response, _ = get(url, transport=transport)
    return json.loads(response.body)


def _candidate(item, source):
    doi = normalize_doi(item.get("DOI"))
    titles, people = item.get("title"), item.get("author")
    if (not isinstance(titles, list) or not titles or not isinstance(titles[0], str) or
            not isinstance(people, list) or not people or any(not isinstance(author, dict) for author in people)):
        raise ValueError("Canonical metadata lacks title, author or publication year")
    title = titles[0].strip()
    authors = []
    for author in people:
        if any(author.get(part) is not None and not isinstance(author.get(part), str) for part in ("given", "family", "name")):
            raise ValueError("Canonical author names must be text")
        name = " ".join((author.get(part) or "").strip() for part in ("given", "family")).strip() or (author.get("name") or "").strip()
        if not name:
            raise ValueError("Canonical metadata lacks a complete author list")
        authors.append(name)
    parts = (item.get("published") or item.get("issued") or {}).get("date-parts", [[]])
    year = parts[0][0] if parts and parts[0] else None
    if not title or not authors or type(year) is not int:
        raise ValueError("Canonical metadata lacks title, author or publication year")
    return {"canonical_id": "doi:" + doi, "doi": doi, "title": title,
            "authors": authors, "year": year, "identity_status": "VERIFIED_METADATA",
            "source_url": source, "discovered_at": now(), "selected_for_acquisition": False,
            "version": item.get("subtype") or item.get("type"), "relations": item.get("relation", {})}


def lookup(doi, *, transport=None):
    doi = normalize_doi(doi)
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    result = _candidate(get_json(url, transport=transport)["message"], url)
    if result["doi"] != doi:
        raise ValueError("Canonical DOI response disagrees with requested DOI")
    return result


def search(query, *, transport=None, rows=20):
    if not str(query).strip() or not isinstance(rows, int) or not 1 <= rows <= 100:
        raise ValueError("Use a nonempty query and 1..100 rows")
    url = "https://api.crossref.org/works?" + urlencode({"query.bibliographic": query, "rows": rows})
    response = get_json(url, transport=transport)
    candidates, rejected, seen = [], [], set()
    for item in response["message"]["items"][:rows]:
        try:
            doi = normalize_doi(item.get("DOI"))
            if doi in seen:
                continue
            seen.add(doi)
            candidates.append(lookup(doi, transport=transport))
        except (ValueError, KeyError, TypeError) as exc:
            rejected.append({"doi": item.get("DOI"), "reason": str(exc)})
    return {"query": query, "source_url": url, "searched_at": now(),
            "candidates": candidates, "rejected": rejected, "coverage": "bounded Crossref candidate search"}


def duplicates(candidates):
    """Only exact DOI/version duplicates; descriptive resemblance never merges records."""
    unique, repeated, seen = [], [], {}
    for candidate in candidates:
        key = (normalize_doi(candidate["doi"]), candidate.get("version"))
        if key in seen:
            old = seen[key]
            fields = ("title", "authors", "year")
            if any(old.get(f) != candidate.get(f) for f in fields):
                raise ValueError("Conflicting metadata for an exact DOI/version identity")
            repeated.append(candidate)
        else:
            seen[key] = candidate
            unique.append(candidate)
    return unique, repeated
