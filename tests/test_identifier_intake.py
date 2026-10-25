"""Offline identifier-to-Vault behavior using real adapters and synthetic PDFs."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

from researchvault import intake, resolution
from researchvault.config import load_settings
from researchvault.discovery import Response
from researchvault.documents import read_record
from researchvault.zotero import Client, publication_identity
try:  # Both `unittest discover -s tests` and explicit module execution.
    from tests.test_pdf_identity import citation_html, pdf_bytes
    from tests.test_zotero import LocalFixture, item
except ModuleNotFoundError:
    from test_pdf_identity import citation_html, pdf_bytes
    from test_zotero import LocalFixture, item


DOI = "10.9999/synthetic-intake"
TITLE = "Synthetic Elastic Memory"
AUTHOR = "Ada Example"
KEY_ENV = "RESEARCHVAULT_SYNTHETIC_TEST_KEY"
ARXIV_BASE = "2401.01234"


def json_response(value, status=200):
    return Response(status, {"Content-Type": "application/json"}, json.dumps(value).encode())


class PublicFixture:
    """Public response bytes only; the production resolver and verifier run."""
    def __init__(self):
        self.calls = []
        self.pdf = pdf_bytes([TITLE, AUTHOR, "2024", "Published version", DOI,
                              "Abstract", "A trial had 6 samples."])
        self.routes = ["https://example.org/synthetic-intake.pdf"]
        self.route_version = "publishedVersion"
        self.pdf_responses = {}
        self.arxiv_pdfs = {version: pdf_bytes([TITLE, AUTHOR, "Abstract", "A trial had 6 samples.",
                                               "arXiv:" + ARXIV_BASE + version + " [cs.RO] 2 Jan 2024"])
                           for version in ("v1", "v2")}

    def __call__(self, method, url, **kwargs):
        if method != "GET":
            raise AssertionError("Public transport must remain read-only")
        self.calls.append(url)
        parsed = urlsplit(url)
        if parsed.hostname == "api.crossref.org":
            requested = unquote(parsed.path.removeprefix("/works/"))
            return json_response({"message": {"DOI": requested, "title": [TITLE],
                                              "author": [{"given": "Ada", "family": "Example"}],
                                              "issued": {"date-parts": [[2024]]}, "type": "journal-article"}})
        if parsed.hostname == "api.unpaywall.org":
            routes = [{"url_for_pdf": route, "url_for_landing_page": "https://example.org/paper",
                       "host_type": "publisher", "version": self.route_version, "license": "cc-by"}
                      for route in self.routes]
            return json_response({"doi": DOI, "is_oa": True,
                                  "best_oa_location": routes[0] if routes else None, "oa_locations": routes})
        if parsed.hostname == "export.arxiv.org":
            exact = parse_qs(parsed.query)["id_list"][0]
            if not exact.endswith(("v1", "v2")):
                exact += "v2"
            atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
                    '<id>https://arxiv.org/abs/' + exact + '</id><title>' + TITLE + '</title>'
                    '<author><name>' + AUTHOR + '</name></author></entry></feed>')
            return Response(200, {"Content-Type": "application/atom+xml"}, atom.encode())
        if parsed.hostname == "arxiv.org" and parsed.path.startswith("/abs/"):
            exact = parsed.path.removeprefix("/abs/")
            html = citation_html(TITLE, [AUTHOR], "https://arxiv.org/pdf/" + ARXIV_BASE,
                                 doi=None, citation_arxiv_id=ARXIV_BASE, citation_online_date="2024/01/02")
            return Response(200, {"Content-Type": "text/html"}, html.encode())
        if parsed.hostname == "arxiv.org" and parsed.path.startswith("/pdf/"):
            exact = parsed.path.removeprefix("/pdf/")
            return Response(200, {"Content-Type": "application/pdf"}, self.arxiv_pdfs[exact[-2:]])
        if url in self.pdf_responses:
            return self.pdf_responses[url]
        if url in self.routes:
            return Response(200, {"Content-Type": "application/pdf"}, self.pdf)
        raise AssertionError("Unexpected injected public request: " + url)


class PipelineLocalFixture(LocalFixture):
    """Official Local API sequence with file-URI readback into temporary storage."""
    def __init__(self, directory):
        super().__init__()
        self.directory = Path(directory)
        self.paths = {}

    def __call__(self, method, url, **kwargs):
        path = urlsplit(url).path
        if method == "GET" and path.endswith("/file/view/url"):
            self.calls.append((method, url, kwargs["headers"], kwargs["body"]))
            key = path.split("/")[-4]
            return Response(200, {"Content-Type": "text/plain", "Zotero-Server-ID": self.server},
                            self.paths[key].as_uri().encode())
        result = super().__call__(method, url, **kwargs)
        if method == "POST" and path == "/api/users/0/items":
            saved = self.items[-1]
            is_attachment = saved["data"]["itemType"] == "attachment"
            count = sum((row["data"]["itemType"] == "attachment") == is_attachment for row in self.items)
            key = ("D" if is_attachment else "P") + f"{count:07d}"
            saved["key"] = saved["data"]["key"] = key
            return Response(result.status, result.headers,
                            json.dumps({"successful": {"0": saved}, "unchanged": {}, "failed": {}}).encode())
        if method == "POST" and path.endswith("/file") and "upload" in parse_qs(kwargs["body"].decode()):
            key = self.last_attachment["key"]
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self.directory / (key + ".pdf")
            target.write_bytes(self.upload)
            self.paths[key] = target.resolve()
        return result

    def add_existing(self, parent, content):
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / "EXISTPDF.pdf"
        target.write_bytes(content)
        self.paths["EXISTPDF"] = target.resolve()
        self.items.extend([item("EXISTPAR", parent), item("EXISTPDF", {
            "itemType": "attachment", "parentItem": "EXISTPAR", "contentType": "application/pdf",
            "md5": hashlib.md5(content, usedforsecurity=False).hexdigest(), "filename": target.name})])


@unittest.skipUnless(importlib.util.find_spec("pypdf"), "Optional pypdf required")
class IdentifierIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        config = self.base / "config.json"
        config.write_text(json.dumps({"vault_root": str(self.base / "vault"),
                                      "runtime_dir": str(self.base / "runtime"), "synthetic": True,
                                      "zotero": {"api_key_env": KEY_ENV},
                                      "acquisition": {"interval": 0}}), encoding="utf-8")
        self.settings = load_settings(config)
        self.public = PublicFixture()
        self.local = PipelineLocalFixture(self.base / "synthetic-zotero-storage")
        self.client = Client("users/0", transport=self.local, api_key_env=KEY_ENV)
        self.environment = patch.dict(os.environ, {KEY_ENV: "synthetic-test-only"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def run_intake(self, inputs=None, **kwargs):
        return intake.run(self.settings, [DOI] if inputs is None else inputs,
                          **{"apply": True, "enabled": True, "allow_zotero_create": True,
                             "email": "synthetic@example.org", "transport": self.public,
                             "client": self.client, "pause": lambda seconds: None, **kwargs})

    def note(self, result):
        return read_record(self.settings.resolve(result["items"][0]["note_path"]), self.settings.vault)

    def test_default_preview_has_no_filesystem_network_or_local_api_effects(self):
        before = sorted(str(path.relative_to(self.base)) for path in self.base.rglob("*"))
        with patch.object(Path, "open", side_effect=AssertionError("preview opened a file")), \
                patch.object(Path, "mkdir", side_effect=AssertionError("preview created a directory")):
            result = self.run_intake([DOI, "arxiv:" + ARXIV_BASE + "v2"], apply=False)
        self.assertEqual(result["status"], "PREVIEW")
        self.assertEqual([row["status"] for row in result["items"]], ["PLANNED", "PLANNED"])
        self.assertEqual(self.public.calls, [])
        self.assertEqual(self.local.calls, [])
        self.assertEqual(before, sorted(str(path.relative_to(self.base)) for path in self.base.rglob("*")))

    def test_readonly_apply_blocks_before_effects(self):
        self.settings.options["read_only"] = True
        with patch.object(Path, "mkdir", side_effect=AssertionError("readonly created a directory")):
            with self.assertRaisesRegex(ValueError, "read-only"):
                self.run_intake()
        self.assertEqual(self.public.calls, [])
        self.assertEqual(self.local.calls, [])
        self.assertFalse(self.settings.runtime.exists())

    def test_real_adapters_reach_reciprocal_note_fulltext_and_canonical_pdf(self):
        from pypdf import PdfReader
        result = self.run_intake()
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertEqual(result["counts"]["parent_created"], 1)
        self.assertEqual(result["counts"]["attachment_created"], 1)
        note = self.note(result)
        fulltext = read_record(self.settings.resolve(note.data["fulltext_path"]), self.settings.vault)
        self.assertEqual(fulltext.data["note_path"], note.relative)
        self.assertEqual(note.data["pdf_path"], str(self.local.paths[note.data["pdf_key"]]))
        self.assertEqual(fulltext.data["pdf_path"], note.data["pdf_path"])
        self.assertEqual(note.data["pdf_sha256"], hashlib.sha256(self.public.pdf).hexdigest())
        reader = PdfReader(io.BytesIO(self.public.pdf), strict=True)
        self.assertEqual(fulltext.body, "\n\n".join(page.extract_text() or "" for page in reader.pages))
        self.assertEqual(note.data["read_status"], "partial")
        self.assertEqual(note.data["analysis_status"], "ANALYSIS_PENDING")
        self.assertEqual(note.data["evidence_status"], "unverified")
        self.assertTrue(result["items"][0]["zotero_read_back_verified"])

    def test_missing_write_credential_retains_verified_download_without_post(self):
        os.environ.pop(KEY_ENV)
        result = self.run_intake()
        self.assertEqual(result["items"][0]["status"], "ZOTERO_WRITE_CREDENTIAL_REQUIRED")
        artifacts = list(self.settings.runtime.glob("intake/artifacts/*.pdf"))
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].read_bytes(), self.public.pdf)
        self.assertFalse(any(call[0] == "POST" for call in self.local.calls))
        self.assertFalse(self.settings.vault.exists())

    def test_resume_is_idempotent_and_requires_explicit_switch(self):
        first = self.run_intake()
        self.assertEqual(first["status"], "COMPLETE", first)
        originals = {path: path.read_bytes() for path in self.settings.vault.rglob("*.md")}
        calls = len(self.public.calls)
        posts = sum(call[0] == "POST" for call in self.local.calls)
        blocked = self.run_intake()
        self.assertEqual(blocked["items"][0]["status"], "RESUME_REQUIRED")
        for _ in range(2):
            repeated = self.run_intake(resume=True)
            self.assertEqual(repeated["status"], "COMPLETE", repeated)
            self.assertEqual(repeated["counts"]["parent_created"], 0)
            self.assertEqual(repeated["counts"]["attachment_created"], 0)
        self.assertEqual(len(self.public.calls), calls)
        self.assertEqual(sum(call[0] == "POST" for call in self.local.calls), posts)
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_exact_arxiv_versions_produce_separate_parents_and_evidence(self):
        for version in ("v1", "v2"):
            result = self.run_intake(["arxiv:" + ARXIV_BASE + version])
            self.assertEqual(result["status"], "COMPLETE", result)
            self.assertEqual(result["counts"]["parent_created"], 1)
        parents = [row for row in self.local.items if row["data"]["itemType"] != "attachment"]
        self.assertEqual({publication_identity(row)["canonical_id"] for row in parents},
                         {"arxiv:" + ARXIV_BASE + "v1", "arxiv:" + ARXIV_BASE + "v2"})
        self.assertEqual(len(list(self.settings.folder("fulltext").glob("*.md"))), 2)

    def test_existing_attachment_is_preferred_without_download_or_writes(self):
        self.local.add_existing({"itemType": "journalArticle", "DOI": DOI, "title": TITLE,
                                 "date": "2024", "creators": [{"creatorType": "author", "lastName": "Example"}]}, self.public.pdf)
        result = self.run_intake(enabled=False, allow_zotero_create=False)
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertEqual(result["counts"]["pdf_reused"], 1)
        self.assertEqual(result["items"][0]["parent_key"], "EXISTPAR")
        self.assertFalse(any(call[0] == "POST" for call in self.local.calls))
        self.assertFalse(any("unpaywall" in url or url in self.public.routes for url in self.public.calls))

    def test_wrong_pdf_cannot_trigger_parent_or_attachment_creation(self):
        self.public.pdf = pdf_bytes([TITLE, AUTHOR, "2024", "Published version", "10.9999/wrong-paper"])
        result = self.run_intake()
        self.assertEqual(result["items"][0]["status"], "PDF_WRONG", result)
        self.assertFalse(any(call[0] == "POST" for call in self.local.calls))
        self.assertFalse(self.settings.vault.exists())

    def test_lawful_route_fallback_reaches_second_verified_pdf(self):
        bad = "https://example.org/unavailable.pdf"
        good = self.public.routes[0]
        self.public.routes = [bad, good]
        self.public.pdf_responses[bad] = Response(404, {"Content-Type": "text/plain"}, b"missing")
        result = self.run_intake()
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertLess(self.public.calls.index(bad), self.public.calls.index(good))
        self.assertEqual(result["items"][0]["pdf"]["source_url"], good)
        events = [json.loads(line) for path in self.settings.runtime.glob("intake/workflows/*/events.jsonl")
                  for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(event["event"] == "route_failed" for event in events))

    def test_missing_oa_route_version_cannot_authorize_import(self):
        self.public.route_version = None
        result = self.run_intake()
        self.assertEqual(result["blocked"], 1, result)
        self.assertFalse(any(call[0] == "POST" for call in self.local.calls))
        self.assertFalse(self.settings.vault.exists())

    def test_pdf_observed_version_must_agree_with_oa_route_version(self):
        self.public.route_version = "acceptedVersion"
        result = self.run_intake()
        self.assertEqual(result["blocked"], 1, result)
        self.assertFalse(any(call[0] == "POST" for call in self.local.calls))
        self.assertFalse(self.settings.vault.exists())

    def test_official_route_cannot_disagree_with_the_verified_selected_version(self):
        def conflicting_route(raw, *, transport):
            candidate = resolution.resolve(raw, transport=transport)
            candidate["lawful_routes"][0]["version"] = "arxiv:" + ARXIV_BASE + "v1"
            return candidate
        result = self.run_intake(["arxiv:" + ARXIV_BASE + "v2"], resolver=conflicting_route)
        self.assertEqual(result["blocked"], 1, result)
        self.assertFalse(any(call[0] == "POST" for call in self.local.calls))
        self.assertFalse(self.settings.vault.exists())

    def test_cached_pdf_tampering_blocks_resume_before_any_mutation(self):
        os.environ.pop(KEY_ENV)
        first = self.run_intake()
        self.assertEqual(first["items"][0]["status"], "ZOTERO_WRITE_CREDENTIAL_REQUIRED")
        artifacts = list(self.settings.runtime.glob("intake/artifacts/*.pdf"))
        artifacts[0].write_bytes(b"%PDF-changed-after-verification")
        os.environ[KEY_ENV] = "synthetic-test-only"
        calls = len(self.public.calls)
        result = self.run_intake(resume=True)
        self.assertEqual(result["items"][0]["status"], "CACHED_PDF_CHANGED", result)
        self.assertEqual(len(self.public.calls), calls)
        self.assertFalse(any(call[0] == "POST" for call in self.local.calls))

    def test_uncertain_parent_receipt_blocks_retry_through_exact_version_alias(self):
        self.local.fail_post = True
        first = self.run_intake(["arxiv:" + ARXIV_BASE])
        self.assertEqual(first["items"][0]["status"], "MANUAL_RECONCILIATION_REQUIRED", first)
        posts = sum(call[0] == "POST" for call in self.local.calls)
        self.local.fail_post = False
        result = self.run_intake(["arxiv:" + ARXIV_BASE + "v2"], resume=True)
        self.assertEqual(result["items"][0]["status"], "MANUAL_RECONCILIATION_REQUIRED", result)
        self.assertEqual(sum(call[0] == "POST" for call in self.local.calls), posts)
        self.assertEqual(self.local.items, [])

    def test_failed_attachment_retains_confirmed_parent_creation_count_and_key(self):
        def fail_attachment(method, url, **kwargs):
            if (method == "POST" and urlsplit(url).path == "/api/users/0/items"
                    and json.loads(kwargs["body"])[0]["itemType"] == "attachment"):
                self.local.calls.append((method, url, kwargs["headers"], kwargs["body"]))
                raise TimeoutError("Synthetic uncertain attachment create")
            return self.local(method, url, **kwargs)
        self.client.transport = fail_attachment
        result = self.run_intake()
        self.assertEqual(result["items"][0]["status"], "MANUAL_RECONCILIATION_REQUIRED", result)
        self.assertEqual(result["counts"]["parent_created"], 1, result)
        self.assertEqual(result["counts"]["attachment_created"], 0)
        parents = [row for row in self.local.items if row["data"]["itemType"] != "attachment"]
        self.assertEqual(len(parents), 1)
        self.assertEqual(result["items"][0]["parent_key"], parents[0]["key"])

    def test_interrupted_pair_publication_resumes_without_duplicate_mutation(self):
        class Interrupted(RuntimeError):
            pass
        def crash(stage):
            if stage == "after_fulltext":
                raise Interrupted()
        with self.assertRaises(Interrupted):
            self.run_intake(crash=crash)
        self.assertEqual(len(list(self.settings.folder("fulltext").glob("*.md"))), 1)
        self.assertEqual(list(self.settings.folder("papers").rglob("*.md")), [])
        posts = sum(call[0] == "POST" for call in self.local.calls)
        result = self.run_intake(resume=True)
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertEqual(sum(call[0] == "POST" for call in self.local.calls), posts)
        note = self.note(result)
        self.assertEqual(read_record(self.settings.resolve(note.data["fulltext_path"]), self.settings.vault).data["note_path"], note.relative)

    def test_user_edited_note_conflict_is_preserved(self):
        first = self.run_intake()
        note = self.note(first)
        target = self.settings.resolve(note.relative)
        user_content = target.read_bytes() + b"\nUser analysis must remain.\n"
        target.write_bytes(user_content)
        posts = sum(call[0] == "POST" for call in self.local.calls)
        result = self.run_intake(resume=True)
        self.assertEqual(result["items"][0]["status"], "VAULT_RECORD_CONFLICT", result)
        self.assertEqual(target.read_bytes(), user_content)
        self.assertEqual(sum(call[0] == "POST" for call in self.local.calls), posts)

    def test_source_bound_analysis_retains_literal_interpretive_and_speculative_labels(self):
        packet = {"pdf_sha256": hashlib.sha256(self.public.pdf).hexdigest(),
                  "facts": [{"statement": "Six samples establish broad robustness.",
                             "quote": "A trial had 6 samples.", "page_index": 1}],
                  "interpretations": ["The evidence may be too narrow for transfer."],
                  "hypotheses": ["Altered body dynamics may change the result."]}
        result = self.run_intake(analysis={"doi:" + DOI: packet})
        self.assertEqual(result["items"][0]["status"], "ARCHIVED", result)
        note = self.note(result)
        self.assertEqual(note.data["analysis_status"], "AGENT_ANALYSIS_CAPTURED")
        self.assertEqual(note.data["read_status"], "partial")
        self.assertEqual(note.data["human_review_status"], "pending")
        self.assertEqual(note.data["evidence_status"], "unverified")
        self.assertIn("[fulltext_verified; text-only]", note.body)
        self.assertIn("agent statement [interpretation; entailment unverified]", note.body)
        self.assertIn("A1 [interpretation]", note.body)
        self.assertIn("H1 [speculative]", note.body)

    def test_analysis_from_another_pdf_cannot_publish_a_note(self):
        packet = {"pdf_sha256": "0" * 64, "interpretations": ["An unbound interpretation."]}
        result = self.run_intake(analysis={"doi:" + DOI: packet})
        self.assertEqual(result["blocked"], 1)
        self.assertEqual(list(self.settings.folder("papers").rglob("*.md")), [])
        self.assertEqual(list(self.settings.folder("fulltext").rglob("*.md")), [])

    def test_pdf_changed_between_readback_and_archive_cannot_publish_records(self):
        archive = intake.fulltext.archive
        changed = []

        def replace_source_before_archive(settings, record, source_path, **kwargs):
            # Simulate a canonical local attachment changing after read_pdf()
            # verified its old bytes, but before archive() reads the file again.
            Path(source_path).write_bytes(pdf_bytes([
                TITLE, AUTHOR, "2024", "Published version", DOI,
                "Abstract", "A trial had 60 samples after source replacement."]))
            changed.append(source_path)
            return archive(settings, record, source_path, **kwargs)

        with patch.object(intake.fulltext, "archive", side_effect=replace_source_before_archive):
            result = self.run_intake()
        self.assertEqual(len(changed), 1)
        self.assertEqual(result["items"][0]["status"], "SOURCE_CHANGED_DURING_ARCHIVE", result)
        self.assertEqual(result["blocked"], 1)
        self.assertEqual(list(self.settings.vault.rglob("*.md")), [])
        self.assertEqual(list(self.settings.folder("metadata").rglob("*.txt")), [])

    def test_existing_pair_bad_fulltext_digest_is_not_reused_through_version_alias(self):
        first = self.run_intake(["arxiv:" + ARXIV_BASE])
        self.assertEqual(first["status"], "COMPLETE", first)
        note = self.note(first)
        fulltext = read_record(self.settings.resolve(note.data["fulltext_path"]), self.settings.vault)
        changed = intake._payload({**fulltext.data, "text_sha256": "0" * 64}, fulltext.body)
        fulltext.path.write_bytes(changed)
        posts = sum(call[0] == "POST" for call in self.local.calls)
        # This exact-version spelling has its own workflow and no publication
        # checkpoint, so it exercises existing-pair reuse instead of staged resume.
        result = self.run_intake(["arxiv:" + ARXIV_BASE + "v2"])
        self.assertEqual(result["items"][0]["status"], "VAULT_RECORD_CONFLICT", result)
        self.assertEqual(fulltext.path.read_bytes(), changed)
        self.assertEqual(sum(call[0] == "POST" for call in self.local.calls), posts)

    def test_existing_pair_bad_note_text_digest_is_not_reused_through_version_alias(self):
        first = self.run_intake(["arxiv:" + ARXIV_BASE])
        self.assertEqual(first["status"], "COMPLETE", first)
        note = self.note(first)
        changed = intake._payload({**note.data, "text_sha256": "0" * 64}, note.body)
        note.path.write_bytes(changed)
        posts = sum(call[0] == "POST" for call in self.local.calls)
        result = self.run_intake(["arxiv:" + ARXIV_BASE + "v2"])
        self.assertEqual(result["items"][0]["status"], "VAULT_RECORD_CONFLICT", result)
        self.assertEqual(note.path.read_bytes(), changed)
        self.assertEqual(sum(call[0] == "POST" for call in self.local.calls), posts)

    def test_existing_pair_broken_reciprocal_link_is_not_reused_through_version_alias(self):
        first = self.run_intake(["arxiv:" + ARXIV_BASE])
        self.assertEqual(first["status"], "COMPLETE", first)
        note = self.note(first)
        fulltext = read_record(self.settings.resolve(note.data["fulltext_path"]), self.settings.vault)
        changed = intake._payload({**fulltext.data, "note_path": "02-papers/Other/missing.md"}, fulltext.body)
        fulltext.path.write_bytes(changed)
        posts = sum(call[0] == "POST" for call in self.local.calls)
        result = self.run_intake(["arxiv:" + ARXIV_BASE + "v2"])
        self.assertEqual(result["items"][0]["status"], "VAULT_RECORD_CONFLICT", result)
        self.assertEqual(fulltext.path.read_bytes(), changed)
        self.assertEqual(sum(call[0] == "POST" for call in self.local.calls), posts)

    def test_per_item_failure_does_not_prevent_other_selected_item(self):
        result = self.run_intake(["not an identifier", DOI])
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["blocked"], 1)
        self.assertEqual(result["items"][1]["status"], "ARCHIVED_ANALYSIS_PENDING", result)
        self.assertEqual(result["counts"]["parent_created"], 1)

    def test_failed_download_identity_does_not_block_another_selected_publication(self):
        self.public.pdf = pdf_bytes([TITLE, AUTHOR, "2024", "Published version", "10.9999/wrong-paper"])
        result = self.run_intake([DOI, "arxiv:" + ARXIV_BASE + "v2"])
        self.assertEqual(result["blocked"], 1, result)
        self.assertEqual(result["items"][0]["status"], "PDF_WRONG")
        self.assertEqual(result["items"][1]["status"], "ARCHIVED_ANALYSIS_PENDING", result)
        self.assertEqual(result["counts"]["parent_created"], 1)
        self.assertEqual(result["counts"]["attachment_created"], 1)


if __name__ == "__main__":
    unittest.main()
