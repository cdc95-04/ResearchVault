"""Synthetic network fixtures, with no personal paper or service traffic."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from researchvault import acquisition, discovery


DOI = "10.9999/synthetic-a"
CANDIDATE = {"canonical_id": "doi:" + DOI, "doi": DOI, "title": "Synthetic Elastic Memory",
             "authors": ["Example"], "year": 2024, "identity_status": "VERIFIED_METADATA", "version": "journal-article"}


def response(data, status=200, headers=None):
    return discovery.Response(status, headers or {"Content-Type": "application/json"}, json.dumps(data).encode())


class IntakeTests(unittest.TestCase):
    def test_canonical_lookup_must_agree(self):
        data = {"message": {"DOI": "10.9999/other", "title": ["Synthetic"], "author": [{"family": "Example"}], "published": {"date-parts": [[2024]]}}}
        with self.assertRaisesRegex(ValueError, "disagrees"):
            discovery.lookup(DOI, transport=lambda *a, **k: response(data))

    def test_discovery_retrieves_canonical_metadata_and_never_pdf(self):
        calls = []
        item = {"DOI": DOI, "title": [CANDIDATE["title"]], "author": [{"family": "Example"}], "issued": {"date-parts": [[2024]]}, "type": "journal-article"}
        def transport(method, url, **kwargs):
            calls.append((method, url))
            return response({"message": {"items": [{"DOI": DOI}, {"DOI": DOI}, {"title": ["No DOI"]}]}} if "?" in url else {"message": item})
        found = discovery.search("elastic memory", transport=transport)
        self.assertEqual(len(calls), 2)
        self.assertEqual(found["candidates"][0]["canonical_id"], "doi:" + DOI)
        self.assertFalse(found["candidates"][0]["selected_for_acquisition"])
        self.assertEqual(len(found["rejected"]), 1)
        self.assertNotIn("pdf", found["candidates"][0])

    def test_missing_authors_is_not_verified_metadata(self):
        item = {"message": {"DOI": DOI, "title": ["Title"], "issued": {"date-parts": [[2024]]}}}
        with self.assertRaises(ValueError):
            discovery.lookup(DOI, transport=lambda *a, **k: response(item))

    def test_exact_duplicates_preserve_versions_and_distinct_dois(self):
        alternative = {**CANDIDATE, "version": "submittedVersion"}
        different = {**CANDIDATE, "doi": "10.9999/b"}
        unique, repeated = discovery.duplicates([CANDIDATE, dict(CANDIDATE), alternative, different])
        self.assertEqual((len(unique), len(repeated)), (3, 1))
        with self.assertRaises(ValueError):
            discovery.duplicates([CANDIDATE, {**CANDIDATE, "year": 2025}])

    def test_public_boundary_rejects_private_credentials_and_sessions(self):
        for url in ("http://example.org/a", "https://127.0.0.1/a", "https://[::1]/a", "https://10.2.3.4/a", "https://example.org:8443/a", "https://user:secret@example.org/a", "https://example.org/a?token=hidden", "https://example.local/a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                discovery.public_url(url)

    def test_dns_private_answer_never_connects(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]), patch("socket.create_connection") as connect:
            with self.assertRaises(ValueError):
                discovery.public_request("GET", "https://example.org/a")
            connect.assert_not_called()

    def test_redirect_checks_every_target(self):
        with self.assertRaises(ValueError):
            discovery.get("https://example.org/a", transport=lambda *a, **k: discovery.Response(302, {"Location": "http://127.0.0.1/private"}, b""))

    def test_injected_responses_still_obey_byte_bound(self):
        with self.assertRaises(ValueError):
            discovery.get("https://example.org/a", max_bytes=3, transport=lambda *a, **k: discovery.Response(200, {}, b"long"))

    def test_identity_states_and_incidental_reference(self):
        main = "Synthetic Elastic Memory\nExample\n2024\nPublished version\n" + DOI
        self.assertEqual(acquisition.assess_identity(main, {}, CANDIDATE)["status"], "VERIFIED")
        self.assertEqual(acquisition.assess_identity("Supplementary Information\n" + main, {}, CANDIDATE)["status"], "SUPPLEMENT")
        self.assertEqual(acquisition.assess_identity(main.replace(DOI, "10.9999/wrong"), {}, CANDIDATE)["status"], "WRONG")
        self.assertEqual(acquisition.assess_identity(main.replace(DOI, "") + "\nReferences\n" + DOI, {}, CANDIDATE)["status"], "PROBABLE")
        self.assertEqual(acquisition.assess_identity(main + " 10.9999/other", {}, CANDIDATE)["status"], "AMBIGUOUS")
        self.assertEqual(acquisition.verify_pdf(b"<html>login</html>", CANDIDATE)["status"], "CORRUPTED")

    def test_later_title_mention_cannot_verify_main_identity(self):
        text = "A different publication\n" + "Unrelated text " * 200 + "\nSynthetic Elastic Memory Example 2024 " + DOI
        self.assertEqual(acquisition.assess_identity(text, {}, CANDIDATE)["status"], "AMBIGUOUS")

    def test_disabled_means_no_state_and_no_network(self):
        result = acquisition.run(None, [], selected=[], transport=lambda *a, **k: self.fail("network called"))
        self.assertEqual(result["status"], "DISABLED")

    def test_unpaywall_preserves_version_and_rejects_wrong_doi(self):
        route = {"url_for_pdf": "https://example.org/a.pdf", "license": "cc-by", "version": "acceptedVersion", "host_type": "repository"}
        data = {"doi": DOI, "is_oa": True, "best_oa_location": route, "oa_locations": [route]}
        found = acquisition.oa_locations(DOI, "synthetic@example.org", transport=lambda *a, **k: response(data))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["version"], "acceptedVersion")
        data["doi"] = "10.9999/other"
        with self.assertRaises(ValueError):
            acquisition.oa_locations(DOI, "synthetic@example.org", transport=lambda *a, **k: response(data))

    def test_selected_serial_resume_manifest_hash_and_tampering(self):
        calls = []
        def transport(method, url, **kwargs):
            calls.append(url)
            if "unpaywall" in url:
                return response({"doi": DOI, "is_oa": True, "best_oa_location": {"url_for_pdf": "https://example.org/a.pdf", "host_type": "publisher", "version": "publishedVersion", "license": "cc-by"}})
            return discovery.Response(200, {"Content-Type": "application/pdf"}, b"%PDF-synthetic-fixture")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = SimpleNamespace(runtime=root / "runtime", vault=root / "vault")
            other = {**CANDIDATE, "doi": "10.9999/b", "canonical_id": "doi:10.9999/b"}
            args = {"selected": [DOI], "enabled": True, "email": "synthetic@example.org", "transport": transport,
                    "verifier": lambda *a: {"status": "VERIFIED", "observed_version": "publishedVersion", "reason": "Synthetic injected identity verification"}}
            first = acquisition.run(settings, [CANDIDATE, other], **args)
            self.assertEqual(len(first["papers"]), 1)
            self.assertEqual(len(calls), 2)
            self.assertTrue(first["papers"][0]["auto_ingest"])
            second = acquisition.run(settings, [CANDIDATE], **args)
            self.assertEqual(len(calls), 2)
            self.assertEqual(first["papers"], second["papers"])
            pdf = next(settings.runtime.rglob("*.pdf"))
            pdf.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "changed"):
                acquisition.run(settings, [CANDIDATE], **args)

    def test_ambiguous_download_never_auto_ingests(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = SimpleNamespace(runtime=Path(temporary) / "runtime", vault=Path(temporary) / "vault")
            with patch.object(acquisition, "oa_locations", return_value=[{"url_for_pdf": "https://example.org/paper.pdf"}]), patch.object(acquisition, "get", return_value=(discovery.Response(200, {"Content-Type": "application/pdf"}, b"%PDF-fixture"), "https://example.org/paper.pdf")):
                result = acquisition.run(settings, [CANDIDATE], selected=[DOI], enabled=True, verifier=lambda *a: {"status": "PROBABLE"})
            self.assertFalse(result["papers"][0]["auto_ingest"])

    def test_runtime_must_not_overlap_vault(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                acquisition.run(SimpleNamespace(runtime=root / "download", vault=root), [], selected=[], enabled=True)

    def test_configured_limits_interval_and_bad_paper_isolation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = SimpleNamespace(runtime=root / "runtime", vault=root / "vault", options={"acquisition": {"max_bytes": 1234, "interval": 0.25}})
            another = {**CANDIDATE, "doi": "10.9999/b", "canonical_id": "doi:10.9999/b"}
            bad = {**CANDIDATE, "doi": "10.9999/c", "identity_status": "unverified"}
            route = {"url_for_pdf": "https://example.org/paper.pdf", "version": "publishedVersion"}
            with patch.object(acquisition, "oa_locations", return_value=[route]), patch.object(acquisition, "get", return_value=(discovery.Response(200, {"Content-Type": "application/pdf"}, b"%PDF-synthetic"), route["url_for_pdf"])) as download, patch.object(acquisition.time, "sleep") as sleep:
                result = acquisition.run(settings, [bad, CANDIDATE, another], selected=[DOI, another["doi"], bad["doi"]], enabled=True,
                                         verifier=lambda *a: {"status": "VERIFIED", "observed_version": "publishedVersion"})
            self.assertEqual([p["status"] for p in result["papers"]], ["VERIFIED", "AMBIGUOUS", "VERIFIED"])
            self.assertTrue(all(c.kwargs["max_bytes"] == 1234 for c in download.call_args_list))
            sleep.assert_called_once_with(0.25)

    def test_doi_match_without_verified_version_is_not_verified(self):
        text = "Synthetic Elastic Memory Example 2024 " + DOI
        self.assertEqual(acquisition.assess_identity(text, {}, CANDIDATE)["status"], "PROBABLE")
        conflicting = "Accepted manuscript\n" + text
        self.assertEqual(acquisition.assess_identity(conflicting, {}, {**CANDIDATE, "expected_version": "publishedVersion"})["status"], "AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()
