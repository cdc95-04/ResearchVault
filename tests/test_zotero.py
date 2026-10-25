"""Behavioral Zotero tests use an in-memory synthetic Local API transport only."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from researchvault.discovery import Response
from researchvault.zotero import Client, MANUAL, publication_identity, publication_match


DOI = "10.9999/synthetic-a"
PARENT = {"itemType": "journalArticle", "title": "Synthetic Elastic Memory", "DOI": DOI,
          "creators": [{"creatorType": "author", "lastName": "Example"}], "date": "2024"}
CANDIDATE = {"doi": DOI, "title": PARENT["title"], "authors": ["Example"], "year": 2024}


def item(key, data):
    return {"key": key, "version": 1, "library": {"type": "user", "id": 0}, "data": {"key": key, **data}}


class LocalFixture:
    def __init__(self, items=(), page_size=100):
        self.items = list(items)
        self.calls = []
        self.page_size = page_size
        self.server = "SYNTHETIC-SERVER"
        self.upload = None
        self.file_hash = None
        self.last_attachment = None
        self.fail_post = False
        self.expected_receipt = None

    def __call__(self, method, url, *, headers, body, max_bytes):
        self.calls.append((method, url, headers, body))
        if method == "POST":
            if self.expected_receipt:
                saved = Path(self.expected_receipt).read_text(encoding="utf-8")
                if '"status": "MUTATION_INTENT"' not in saved:
                    raise AssertionError("Mutation happened before durable intent")
            if self.fail_post:
                raise TimeoutError("Synthetic uncertain network outcome")
        path, query = urlsplit(url).path, parse_qs(urlsplit(url).query)
        result_headers = {"Zotero-Server-ID": self.server, "Last-Modified-Version": "1", "Content-Type": "application/json"}
        status, data = 200, {}
        if method == "GET" and path == "/api/users/0/items":
            if query.get("sort") != ["dateAdded"] or query.get("direction") != ["asc"]:
                raise AssertionError("Unsupported Local API inventory sort")
            start = int(query.get("start", ["0"])[0])
            data = self.items[start:start + self.page_size]
            result_headers["Total-Results"] = str(len(self.items))
        elif method == "GET" and path == "/api/items/new":
            # The real Local API has no Web API new-item template route.
            status, result_headers = 404, {}
        elif method == "POST" and path == "/api/users/0/items":
            submitted = json.loads(body)[0]
            key = "PARENT01" if submitted["itemType"] != "attachment" else "PDF00001"
            saved = item(key, submitted)
            self.items.append(saved)
            if submitted["itemType"] == "attachment":
                self.last_attachment = saved
            data = {"successful": {"0": saved}, "unchanged": {}, "failed": {}}
        elif method == "POST" and path.endswith("/file"):
            form = parse_qs(body.decode())
            if "upload" in form:
                self.last_attachment["data"]["md5"] = self.file_hash
                status, data = 204, None
            else:
                self.file_hash = form["md5"][0]
                data = {"url": "http://127.0.0.1:23119/api/local/uploads/synthetic-upload", "uploadKey": "synthetic-upload", "prefix": "", "suffix": "", "contentType": "application/octet-stream"}
        elif method == "POST" and path.startswith("/api/local/uploads/"):
            self.upload = body
            status, data = 201, None
            result_headers.pop("Zotero-Server-ID")
        elif method == "GET" and "/items/" in path:
            key = path.rsplit("/", 1)[-1]
            matches = [i for i in self.items if i["key"] == key]
            if not matches:
                status = 404
            else:
                data = matches[0]
        else:
            raise AssertionError("Unexpected synthetic API request " + method + " " + path)
        return Response(status, result_headers, b"" if data is None else json.dumps(data).encode())


class ZoteroTests(unittest.TestCase):
    def arxiv_parent(self, identifier="2401.01234v2", **extra):
        return {"itemType": "preprint", "title": PARENT["title"], "creators": PARENT["creators"],
                "date": "2024", "url": "https://arxiv.org/abs/" + identifier,
                "extra": "arXiv: " + identifier, **extra}

    def test_public_arxiv_identity_accepts_standard_fields_and_candidate_metadata(self):
        expected = "2401.01234v2"
        for data in ({"url": "https://arxiv.org/abs/" + expected}, {"archiveID": expected},
                     {"extra": "Other information\narXiv ID: " + expected + " [cs.RO]"},
                     {"arxiv_id_version": expected}, {"arxiv_id": expected},
                     {"arxiv": expected, "doi": "10.48550/arXiv.2401.01234"}):
            for supplied in (data, item("PARENT01", data)):
                with self.subTest(data=data, envelope="data" in supplied):
                    identity = publication_identity(supplied)
                    self.assertEqual(identity["canonical_id"], "arxiv:" + expected)
                    self.assertEqual(identity["arxiv_id"], "2401.01234")
                    self.assertEqual(identity["arxiv_id_version"], expected)

    def test_arxiv_unknown_versions_and_conflicts_are_not_exact_identities(self):
        for data in ({"url": "https://arxiv.org/abs/2401.01234"},
                     {"DOI": "10.48550/arXiv.2401.01234"}):
            self.assertIsNone(publication_identity(data)["canonical_id"])
            self.assertEqual(publication_match(self.arxiv_parent(), data), "AMBIGUOUS")
        for data in ({"arxiv_id_version": "2401.01234v2", "extra": "arXiv: 2401.01234v1"},
                     {"url": "https://arxiv.org/abs/2401.01234v2", "archiveID": "2401.99999v2"}):
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, "Conflicting arXiv"):
                publication_identity(data)

    def test_arxiv_versioned_identity_never_merges_a_related_journal_doi(self):
        preprint = self.arxiv_parent(DOI="10.48550/arXiv.2401.01234")
        journal = {**PARENT, "extra": "arXiv: 2401.01234v2"}
        self.assertEqual(publication_identity(journal)["canonical_id"], "doi:" + DOI)
        self.assertEqual(publication_match(preprint, journal), "DISTINCT")
        self.assertEqual(publication_match(preprint, self.arxiv_parent("2401.01234v1", DOI="10.48550/arXiv.2401.01234")), "DISTINCT")

    def test_arxiv_create_plan_reuses_only_the_exact_version(self):
        proposed = self.arxiv_parent()
        fixture = LocalFixture([item("PARENT01", proposed)])
        result = Client("users/0", transport=fixture).create_item(proposed)
        self.assertEqual(result["status"], "EXISTS")
        self.assertEqual({call[0] for call in fixture.calls}, {"GET"})
        fixture = LocalFixture([item("PARENT01", self.arxiv_parent("2401.01234v1"))])
        result = Client("users/0", transport=fixture).create_item(proposed)
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual({call[0] for call in fixture.calls}, {"GET"})

    def test_existing_arxiv_pdf_title_does_not_merge_or_block_another_exact_version(self):
        fixture = LocalFixture([item("PARENT01", self.arxiv_parent("2401.01234v1")),
                                item("PDF00001", {"itemType": "attachment", "parentItem": "PARENT01",
                                                 "contentType": "application/pdf", "title": PARENT["title"]})])
        result = Client("users/0", transport=fixture).create_item(self.arxiv_parent("2401.01234v2"))
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual({call[0] for call in fixture.calls}, {"GET"})
        self.assertEqual(len(fixture.items), 2)

    def test_unversioned_arxiv_parent_stops_creation_without_mutations(self):
        fixture = LocalFixture([item("PARENT01", self.arxiv_parent("2401.01234"))])
        result = Client("users/0", transport=fixture).create_item(self.arxiv_parent(), apply=True)
        self.assertEqual(result["status"], "AMBIGUOUS")
        self.assertEqual({call[0] for call in fixture.calls}, {"GET"})
        with self.assertRaisesRegex(ValueError, "exact arXiv version"):
            Client("users/0", transport=LocalFixture()).create_item(self.arxiv_parent("2401.01234"))

    def test_arxiv_create_keeps_existing_receipt_and_readback_contract(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"ZOTERO_API_KEY": "synthetic-key-for-test"}):
            receipt = Path(temporary) / "arxiv.jsonl"
            fixture = LocalFixture()
            fixture.expected_receipt = receipt
            client = Client("users/0", transport=fixture)
            result = client.create_item(self.arxiv_parent(), apply=True, receipt_path=receipt)
            self.assertEqual(result["status"], "CREATED")
            self.assertEqual(publication_identity(result["item"])["canonical_id"], "arxiv:2401.01234v2")
            self.assertIn('"status": "COMPLETE"', receipt.read_text())
            count = len(fixture.calls)
            self.assertEqual(client.create_item(self.arxiv_parent(), apply=True, receipt_path=receipt)["status"], MANUAL)
            self.assertEqual(len(fixture.calls), count)

    def test_missing_arxiv_identity_at_parent_readback_stops_as_uncertain(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"ZOTERO_API_KEY": "synthetic-key-for-test"}):
            proposed = self.arxiv_parent()
            proposed.pop("url")
            fixture = LocalFixture()
            def stripped(method, url, **kwargs):
                result = fixture(method, url, **kwargs)
                if method == "GET" and urlsplit(url).path.endswith("/items/PARENT01"):
                    saved = json.loads(result.body)
                    saved["data"].pop("extra")
                    return Response(result.status, result.headers, json.dumps(saved).encode())
                return result
            receipt = Path(temporary) / "arxiv.jsonl"
            result = Client("users/0", transport=stripped).create_item(proposed, apply=True, receipt_path=receipt)
            self.assertEqual(result["status"], MANUAL)
            self.assertIn("MANUAL_RECONCILIATION_REQUIRED", receipt.read_text())

    def test_arxiv_pdf_import_requires_exact_parent_version_and_preserves_pdfs(self):
        candidate = {"arxiv_id_version": "2401.01234v2", "title": PARENT["title"]}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"ZOTERO_API_KEY": "synthetic-key-for-test"}):
            pdf = Path(temporary) / "synthetic.pdf"
            pdf.write_bytes(b"%PDF-synthetic-arxiv")
            for identifier in ("2401.01234v1", "2401.01234"):
                fixture = LocalFixture([item("PARENT01", self.arxiv_parent(identifier))])
                with self.subTest(identifier=identifier), self.assertRaisesRegex(ValueError, "publication/version"):
                    Client("users/0", transport=fixture).import_pdf("PARENT01", pdf, candidate, verifier=lambda *a: {"status": "VERIFIED"})
                self.assertEqual({call[0] for call in fixture.calls}, {"GET"})
            fixture = LocalFixture([item("PARENT01", self.arxiv_parent())])
            client = Client("users/0", transport=fixture)
            result = client.import_pdf("PARENT01", pdf, candidate, apply=True,
                                       receipt_path=Path(temporary) / "pdf.jsonl", verifier=lambda *a: {"status": "VERIFIED"})
            self.assertEqual(result["status"], "CREATED")
            result = client.import_pdf("PARENT01", pdf, candidate, verifier=lambda *a: {"status": "VERIFIED"})
            self.assertEqual(result["status"], "EXISTS")

    def test_inventory_reads_every_page_including_attachments(self):
        items = [item("PARENT01", PARENT), item("PDF00001", {"itemType": "attachment", "parentItem": "PARENT01", "contentType": "application/pdf"}), item("ANNOT001", {"itemType": "annotation", "parentItem": "PDF00001"})]
        fixture = LocalFixture(items, page_size=1)
        result = Client("user:0", transport=fixture).inventory()
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(len(fixture.calls), 3)

    def test_inventory_rejects_wrong_namespace_and_duplicate_pages(self):
        wrong = item("PARENT01", PARENT)
        wrong["library"] = {"type": "group", "id": 0}
        with self.assertRaises(ValueError):
            Client("users/0", transport=LocalFixture([wrong])).inventory()
        duplicated = [item("PARENT01", PARENT)] * 2
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            Client("users/0", transport=LocalFixture(duplicated, page_size=1)).inventory()

    def test_inventory_rejects_changing_server_or_library_version(self):
        for changed in ("server", "version"):
            fixture = LocalFixture([item("PARENT01", PARENT), item("PARENT02", {**PARENT, "DOI": "10.9999/b"})], page_size=1)
            def unstable(*a, **k):
                response = fixture(*a, **k)
                if len(fixture.calls) == 2:
                    response.headers["Zotero-Server-ID" if changed == "server" else "Last-Modified-Version"] = "changed"
                return response
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                Client("users/0", transport=unstable).inventory()

    def test_find_pdf_is_readonly_and_explicit_keys_do_not_fall_through(self):
        fixture = LocalFixture([item("PARENT01", PARENT), item("PDF00001", {"itemType": "attachment", "parentItem": "PARENT01", "contentType": "application/pdf"})])
        client = Client("users/0", transport=fixture)
        self.assertEqual(client.find_pdf(doi=DOI)["status"], "FOUND")
        with self.assertRaisesRegex(ValueError, "no fallback"):
            client.find_pdf(zotero_key="MISSING1", doi=DOI)
        with self.assertRaises(ValueError):
            client.find_pdf(zotero_key="PARENT01", pdf_key="MISSING2")
        self.assertEqual({c[0] for c in fixture.calls}, {"GET"})

    def test_multiple_pdfs_or_parents_are_ambiguous(self):
        fixture = LocalFixture([item("PARENT01", PARENT), item("PARENT02", PARENT)])
        self.assertEqual(Client("users/0", transport=fixture).find_pdf(doi=DOI)["status"], "AMBIGUOUS")

    def test_default_create_is_dry_run_without_credentials(self):
        fixture = LocalFixture()
        result = Client("users/0", transport=fixture).create_item(PARENT)
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual({c[0] for c in fixture.calls}, {"GET"})

    def test_existing_parent_preserved_and_title_is_only_a_hint(self):
        fixture = LocalFixture([item("PARENT01", PARENT)])
        self.assertEqual(Client("users/0", transport=fixture).create_item(PARENT, apply=True)["status"], "EXISTS")
        proposed = {**PARENT, "DOI": "10.9999/other-version"}
        self.assertEqual(Client("users/0", transport=fixture).create_item(proposed)["status"], "AMBIGUOUS")
        self.assertFalse(any(call[0] == "POST" for call in fixture.calls))

    def test_doi_less_pmlr_paper_uses_exact_volume_and_slug_identity(self):
        proposed = {k: v for k, v in PARENT.items() if k != "DOI"}
        proposed["url"] = "https://proceedings.mlr.press/v306/example26a.html"
        fixture = LocalFixture([item("PARENT01", proposed)])
        result = Client("users/0", transport=fixture).create_item(proposed, apply=True)
        self.assertEqual(result["status"], "EXISTS")
        self.assertFalse(any(c[0] == "POST" for c in fixture.calls))
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"ZOTERO_API_KEY": "synthetic-key-for-test"}):
            result = Client("users/0", transport=LocalFixture()).create_item(proposed, apply=True, receipt_path=Path(temporary) / "receipt.jsonl")
            self.assertEqual(result["status"], "CREATED")

    def test_general_or_noncanonical_url_does_not_replace_stable_identity(self):
        proposed = {k: v for k, v in PARENT.items() if k != "DOI"}
        for url in ("https://example.org/paper", "http://proceedings.mlr.press/v306/example26a.html", "https://proceedings.mlr.press/v306/example26a.html?download=1", "https://proceedings.mlr.press:443/v306/example26a.html"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "canonical publisher"):
                Client("users/0", transport=LocalFixture()).create_item({**proposed, "url": url})

    def test_conflicting_doi_at_same_publisher_identity_blocks_create(self):
        proposed = {**PARENT, "url": "https://proceedings.mlr.press/v306/example26a.html"}
        fixture = LocalFixture([item("PARENT01", {**proposed, "DOI": "10.9999/other"})])
        result = Client("users/0", transport=fixture).create_item(proposed, apply=True)
        self.assertEqual(result["status"], "AMBIGUOUS")
        self.assertFalse(any(c[0] == "POST" for c in fixture.calls))

    def test_official_paper_identifiers_preserve_doi_less_publication_identity(self):
        proposed = {k: v for k, v in PARENT.items() if k != "DOI"}
        urls = [
            "https://proceedings.iclr.cc/paper_files/paper/2024/hash/" + "a" * 32 + "-Abstract-Conference.html",
            "https://openaccess.thecvf.com/content/CVPR2024/html/Example_Method_CVPR_2024_paper.html",
        ]
        for url in urls:
            with self.subTest(url=url):
                fixture = LocalFixture([item("PARENT01", {**proposed, "url": url})])
                self.assertEqual(Client("users/0", transport=fixture).create_item({**proposed, "url": url})["status"], "EXISTS")

    def test_create_needs_env_key_and_never_accepts_existing_key(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                Client("users/0", transport=LocalFixture()).create_item(PARENT, apply=True, receipt_path=Path(temporary) / "intent.jsonl")
        with self.assertRaises(ValueError):
            Client("users/0", transport=LocalFixture()).create_item({**PARENT, "key": "PARENT01"})

    def test_create_persists_intent_before_post_and_confirms_readback(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"ZOTERO_API_KEY": "synthetic-key-for-test"}):
            receipt = Path(temporary) / "intent.jsonl"
            fixture = LocalFixture()
            fixture.expected_receipt = receipt
            callbacks = []
            result = Client("users/0", transport=fixture).create_item(PARENT, apply=True, receipt_path=receipt, persist=lambda e: callbacks.append(e))
            self.assertEqual(result["status"], "CREATED")
            self.assertEqual(len(callbacks), 1)
            post = next(c for c in fixture.calls if c[0] == "POST")
            self.assertEqual(post[2]["Zotero-Server-ID"], "SYNTHETIC-SERVER")
            self.assertEqual(post[2]["If-Unmodified-Since-Version"], "1")
            payload = json.loads(post[3])[0]
            self.assertEqual((payload["tags"], payload["collections"], payload["relations"]), ([], [], {}))
            self.assertFalse(any("/items/new" in call[1] for call in fixture.calls))
            self.assertNotIn("synthetic-key-for-test", receipt.read_text())
            self.assertIn('"status": "COMPLETE"', receipt.read_text())

    def test_uncertain_outcome_blocks_retry_even_with_fresh_client(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"ZOTERO_API_KEY": "synthetic-key-for-test"}):
            fixture = LocalFixture()
            fixture.fail_post = True
            path = Path(temporary) / "intent.jsonl"
            first = Client("users/0", transport=fixture).create_item(PARENT, apply=True, receipt_path=path)
            self.assertEqual(first["status"], MANUAL)
            count = len(fixture.calls)
            second = Client("users/0", transport=fixture).create_item(PARENT, apply=True, receipt_path=path)
            self.assertEqual(second["status"], MANUAL)
            self.assertEqual(len(fixture.calls), count)

    def test_failed_persistence_callback_blocks_mutation(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"ZOTERO_API_KEY": "synthetic-key-for-test"}):
            fixture = LocalFixture()
            def fail(event):
                raise OSError("Synthetic persistence failure")
            result = Client("users/0", transport=fixture).create_item(PARENT, apply=True, receipt_path=Path(temporary) / "receipt.jsonl", persist=fail)
            self.assertEqual(result["status"], MANUAL)
            self.assertFalse(any(c[0] == "POST" for c in fixture.calls))

    def test_conditional_upload_readback_and_existing_annotations_preserved(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"ZOTERO_API_KEY": "synthetic-key-for-test"}):
            directory = Path(temporary)
            pdf = directory / "synthetic.pdf"
            pdf.write_bytes(b"%PDF-synthetic-content")
            fixture = LocalFixture([item("PARENT01", PARENT)])
            path = directory / "receipt.jsonl"
            fixture.expected_receipt = path
            client = Client("users/0", transport=fixture)
            result = client.import_pdf("PARENT01", pdf, CANDIDATE, apply=True, receipt_path=path, verifier=lambda *a: {"status": "VERIFIED"})
            self.assertEqual(result["status"], "CREATED")
            self.assertEqual(fixture.upload, pdf.read_bytes())
            writes = [c for c in fixture.calls if c[0] == "POST"]
            self.assertEqual(len(writes), 4)
            conditional = [c for c in writes if c[1].endswith("/file")]
            self.assertTrue(all(c[2]["If-None-Match"] == "*" for c in conditional))
            upload = next(c for c in writes if "/local/uploads/" in c[1])
            self.assertNotIn("Zotero-API-Key", upload[2])
            self.assertNotIn("Zotero-Server-ID", upload[2])
            fixture.items.append(item("ANNOT001", {"itemType": "annotation", "parentItem": "PDF00001", "annotationText": "Synthetic annotation"}))
            before = json.dumps(fixture.items, sort_keys=True)
            result = client.import_pdf("PARENT01", pdf, CANDIDATE, apply=True, receipt_path=directory / "another.jsonl", verifier=lambda *a: {"status": "VERIFIED"})
            self.assertEqual(result["status"], "EXISTS")
            self.assertEqual(before, json.dumps(fixture.items, sort_keys=True))

    def test_unverified_pdf_cannot_create_attachment(self):
        with tempfile.TemporaryDirectory() as temporary:
            pdf = Path(temporary) / "synthetic.pdf"
            pdf.write_bytes(b"%PDF-synthetic")
            fixture = LocalFixture([item("PARENT01", PARENT)])
            with self.assertRaises(ValueError):
                Client("users/0", transport=fixture).import_pdf("PARENT01", pdf, CANDIDATE, apply=True, verifier=lambda *a: {"status": "PROBABLE"})
            self.assertEqual(fixture.calls, [])

    def test_api_origin_and_mutation_methods_are_bounded(self):
        for origin in ("http://example.org:23119/api", "http://127.0.0.1:80/api", "file:///tmp/database"):
            with self.assertRaises(ValueError):
                Client("users/0", base_url=origin)
        client = Client("users/0", transport=lambda *a, **k: self.fail("transport called"))
        with self.assertRaises(ValueError):
            client._request("DELETE", client._url("/items/PARENT01"))

    def test_http_failure_without_server_id_reports_actual_status(self):
        client = Client("users/0", transport=LocalFixture())
        client.inventory()
        with self.assertRaisesRegex(ValueError, "HTTP 404"):
            client._get(client.base_url + "/items/new?itemType=journalArticle")

    def test_upload_rejects_a_conflicting_server_id(self):
        with patch.dict(os.environ, {"ZOTERO_API_KEY": "synthetic-key-for-test"}):
            client = Client("users/0", transport=lambda *a, **k: Response(201, {"Zotero-Server-ID": "OTHER"}, b""))
            client.server_id = "EXPECTED"
            with self.assertRaisesRegex(ValueError, "Server ID"):
                client._request("POST", client.base_url + "/local/uploads/synthetic", upload=True)


class ReadPdfTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.pdf = Path(self.directory.name) / "synthetic source.pdf"
        self.content = b"%PDF-synthetic-local-attachment"
        self.pdf.write_bytes(self.content)
        self.attachment = {"itemType": "attachment", "parentItem": "PARENT01", "contentType": "application/pdf",
                           "md5": hashlib.md5(self.content, usedforsecurity=False).hexdigest()}

    def fixture(self, *, uri=None, attachment=None, parents=None, status=200, media="text/plain; charset=utf-8", server="SYNTHETIC-SERVER"):
        rows = [item("PARENT01", PARENT)] if parents is None else parents
        fixture = LocalFixture([*rows, item("PDF00001", self.attachment if attachment is None else attachment)])
        def transport(method, url, **kwargs):
            if urlsplit(url).path.endswith("/file/view/url"):
                fixture.calls.append((method, url, kwargs["headers"], kwargs["body"]))
                return Response(status, {"Content-Type": media, "Zotero-Server-ID": server},
                                (self.pdf.as_uri() if uri is None else uri).encode())
            return fixture(method, url, **kwargs)
        return fixture, transport

    def test_reads_exact_local_pdf_via_official_endpoint_in_readonly_mode(self):
        fixture, transport = self.fixture()
        result = Client("users/0", transport=transport, read_only=True).read_pdf("PDF00001", parent_key="PARENT01")
        self.assertEqual(result, {"path": str(self.pdf.resolve()), "content": self.content,
                                 "sha256": hashlib.sha256(self.content).hexdigest(), "md5": self.attachment["md5"],
                                 "pdf_key": "PDF00001", "zotero_key": "PARENT01", "library": "users/0",
                                 "server_id": "SYNTHETIC-SERVER"})
        self.assertEqual({call[0] for call in fixture.calls}, {"GET"})
        self.assertTrue(fixture.calls[-1][1].endswith("/items/PDF00001/file/view/url"))
        self.assertEqual(self.pdf.read_bytes(), self.content)

    def test_exact_parent_pdf_and_complete_namespace_are_required_before_file_endpoint(self):
        cases = [({"parent_key": "PARENT02"}, {}),
                 ({}, {"attachment": {**self.attachment, "contentType": "text/html"}}),
                 ({}, {"attachment": {**self.attachment, "itemType": "note"}}),
                 ({}, {"attachment": {**self.attachment, "key": "OTHER001"}}),
                 ({}, {"parents": []}),
                 ({}, {"attachment": {k: v for k, v in self.attachment.items() if k != "md5"}})]
        for arguments, options in cases:
            fixture, transport = self.fixture(**options)
            with self.subTest(arguments=arguments, options=options), self.assertRaises(ValueError):
                Client("users/0", transport=transport).read_pdf("PDF00001", **arguments)
            self.assertFalse(any(call[1].endswith("/file/view/url") for call in fixture.calls))
        fixture, transport = self.fixture()
        with self.assertRaisesRegex(ValueError, "not found"):
            Client("users/0", transport=transport).read_pdf("MISSING1")
        fixture, transport = self.fixture()
        fixture.items[1]["library"] = {"type": "group", "id": 2}
        with self.assertRaisesRegex(ValueError, "library type"):
            Client("users/0", transport=transport).read_pdf("PDF00001")

    def test_rejects_remote_relative_session_and_share_file_uris(self):
        for uri in ("https://example.org/paper.pdf", "file://server/share/paper.pdf", "file://localhost/C:/paper.pdf",
                    "file:relative.pdf", "file:////server/share/paper.pdf", "file:///%2Fserver/share/paper.pdf",
                    self.pdf.as_uri().replace("file:///", "file:/", 1), self.pdf.as_uri() + "?",
                    self.pdf.as_uri() + "?token=secret", self.pdf.as_uri() + "#page=1"):
            fixture, transport = self.fixture(uri=uri)
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                Client("users/0", transport=transport).read_pdf("PDF00001")
            self.assertEqual({call[0] for call in fixture.calls}, {"GET"})

    def test_file_endpoint_status_media_and_server_identity_must_agree(self):
        for options in ({"status": 204}, {"media": "application/json"}, {"server": "OTHER"}):
            _, transport = self.fixture(**options)
            with self.subTest(options=options), self.assertRaises(ValueError):
                Client("users/0", transport=transport).read_pdf("PDF00001")

    def test_local_bytes_must_match_pdf_signature_and_inventory_hash(self):
        for content in (b"%PDF-tampered", b"<html>not a PDF</html>"):
            self.pdf.write_bytes(content)
            _, transport = self.fixture()
            with self.subTest(content=content), self.assertRaises(ValueError):
                Client("users/0", transport=transport).read_pdf("PDF00001")
        self.pdf.unlink()
        _, transport = self.fixture()
        with self.assertRaises(OSError):
            Client("users/0", transport=transport).read_pdf("PDF00001")

    def test_size_limit_is_checked_before_file_read_and_again_after_read(self):
        _, transport = self.fixture()
        with patch.object(Path, "open", side_effect=AssertionError("oversize file opened")):
            with self.assertRaisesRegex(ValueError, "byte limit"):
                Client("users/0", transport=transport).read_pdf("PDF00001", max_bytes=2)
        _, transport = self.fixture()
        with patch.object(Path, "open", return_value=io.BytesIO(self.content + b"growth")):
            with self.assertRaisesRegex(ValueError, "size invalid"):
                Client("users/0", transport=transport).read_pdf("PDF00001", max_bytes=len(self.content))
        for limit in (0, -1, True, 1.5):
            fixture, transport = self.fixture()
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, "positive integer"):
                Client("users/0", transport=transport).read_pdf("PDF00001", max_bytes=limit)
            self.assertEqual(fixture.calls, [])


if __name__ == "__main__":
    unittest.main()
