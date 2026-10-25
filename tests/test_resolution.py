"""Identifier and official-source resolution through synthetic GET responses."""
import hashlib
import html
import json
import unittest

from researchvault import discovery, resolution


DOI = "10.9999/synthetic-a"
BASE = "2408.06316"
TITLE = "Active Exploration for System Identification"
AUTHORS = ["Marius Memmel", "Andrew Wagenmaker"]


def response(body, media="text/html", status=200, headers=None):
    return discovery.Response(status, headers or {"Content-Type": media}, body.encode("utf-8"))


def citation(title=TITLE, authors=AUTHORS, pdf=None, year="2024/08/12", doi=None, arxiv=None):
    values = [("citation_title", title), *(("citation_author", author) for author in authors),
              ("citation_publication_date", year), ("citation_online_date", year)]
    if pdf:
        values.append(("citation_pdf_url", pdf))
    if doi:
        values.append(("citation_doi", doi))
    if arxiv:
        values.append(("citation_arxiv_id", arxiv))
    return "<html><head>" + "".join(
        f'<meta name="{name}" content="{html.escape(value, quote=True)}">' for name, value in values
    ) + "</head><body>Actual captured fixture</body></html>"


def atom(version="v2", *, title=TITLE, authors=AUTHORS, related_doi=None):
    names = "".join(f"<author><name>{html.escape(name)}</name></author>" for name in authors)
    related = f"<arxiv:doi>{related_doi}</arxiv:doi>" if related_doi else ""
    return ('<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">'
            f'<entry><id>http://arxiv.org/abs/{BASE}{version}</id><title>{html.escape(title)}</title>'
            f'{names}<published>2024-08-12T00:00:00Z</published><updated>2025-01-02T00:00:00Z</updated>{related}</entry></feed>')


class Fixture:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method != "GET" or kwargs.get("body") is not None:
            raise AssertionError("Only GET metadata reads are permitted")
        if url not in self.routes:
            raise AssertionError("Unexpected metadata URL: " + url)
        return self.routes[url]


class ParseTests(unittest.TestCase):
    def test_doi_forms_and_percent_encoded_doi_url_have_one_identity(self):
        variants = [DOI, "DOI: " + DOI.upper(), "https://DOI.ORG/10.9999%2Fsynthetic-a",
                    "http://dx.doi.org/" + DOI]
        for value in variants:
            with self.subTest(value=value):
                self.assertEqual(resolution.parse(value)["canonical_id"], "doi:" + DOI)

    def test_arxiv_aliases_preserve_exact_version(self):
        variants = [BASE + "v2", "arXiv:" + BASE + "v2", "https://arxiv.org/abs/" + BASE + "v2",
                    "https://arxiv.org/pdf/" + BASE + "v2.pdf"]
        for value in variants:
            with self.subTest(value=value):
                self.assertEqual(resolution.parse(value)["arxiv_id_version"], BASE + "v2")
        self.assertNotEqual(resolution.parse(BASE + "v1")["canonical_id"], resolution.parse(BASE + "v2")["canonical_id"])
        self.assertIsNone(resolution.parse(BASE)["arxiv_id_version"])

    def test_registered_arxiv_doi_uses_arxiv_resolution(self):
        parsed = resolution.parse("https://doi.org/10.48550/arXiv." + BASE)
        self.assertEqual(parsed["kind"], "arxiv")
        self.assertEqual(parsed["arxiv_id"], BASE)

    def test_unsafe_and_unsupported_inputs_stop_before_transport(self):
        fixture = Fixture({})
        cases = ["https://example.org/paper.pdf", "https://127.0.0.1/paper", "https://doi.org/" + DOI + "?utm_source=test",
                 "https://arxiv.org/abs/" + BASE + "#section", "https://secret@arxiv.org/abs/" + BASE,
                 "https://arxiv.org:8443/abs/" + BASE, "https://proceedings.mlr.press/v1/a.html?token=hidden",
                 "https://arxiv.org.evil.example/abs/" + BASE, "https://arxiv.org/abs/" + BASE + "%0a",
                 "hep-th/9901001v2", "arxiv:2413.00001v1", "", None]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolution.resolve(value, transport=fixture)
        self.assertEqual(fixture.calls, [])

    def test_supported_official_publishers_have_canonical_landing_identities(self):
        sources = ["https://proceedings.mlr.press/v306/wang26gs.html",
                   "https://proceedings.neurips.cc/paper_files/paper/2024/hash/" + "a" * 32 + "-Abstract-Conference.html",
                   "https://proceedings.iclr.cc/paper_files/paper/2024/hash/" + "a" * 32 + "-Abstract-Conference.html",
                   "https://openaccess.thecvf.com/content/CVPR2024/html/Example_Method_CVPR_2024_paper.html"]
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(resolution.parse(source)["canonical_url"], source)


class ResolutionTests(unittest.TestCase):
    def arxiv_fixture(self, requested=BASE + "v2", returned="v2", **changes):
        source = "https://arxiv.org/abs/" + BASE + returned
        pdf = "https://arxiv.org/pdf/" + BASE
        captured = citation(pdf=pdf, arxiv=BASE, **changes)
        api = "https://export.arxiv.org/api/query?id_list=" + requested
        fixture = Fixture({api: response(atom(returned, related_doi=DOI), "application/atom+xml"), source: response(captured)})
        return fixture, source, captured

    def test_arxiv_exact_version_uses_real_captured_html_and_related_doi_stays_separate(self):
        fixture, source, captured = self.arxiv_fixture()
        candidate = resolution.resolve(BASE + "v2", transport=fixture)
        self.assertEqual(candidate["canonical_id"], "arxiv:" + BASE + "v2")
        self.assertEqual(candidate["authors"], AUTHORS)
        self.assertIsNone(candidate["doi"])
        self.assertEqual(candidate["related_doi"], DOI)
        self.assertEqual(candidate["source_evidence"]["html"], captured)
        self.assertEqual(candidate["source_evidence"]["html_sha256"], hashlib.sha256(captured.encode()).hexdigest())
        self.assertNotIn("sha256", candidate["source_evidence"])
        self.assertEqual(candidate["lawful_routes"][0]["url"], "https://arxiv.org/pdf/" + BASE + "v2")
        self.assertEqual(candidate["source_url"], source)
        self.assertEqual(candidate["identity_status"], "VERIFIED_METADATA")
        self.assertTrue(all(item["sha256"] for item in candidate["sources"]))
        self.assertEqual(len(fixture.calls), 2)

    def test_unversioned_arxiv_resolves_to_recorded_exact_version(self):
        fixture, source, _ = self.arxiv_fixture(requested=BASE)
        candidate = resolution.resolve(BASE, transport=fixture)
        self.assertEqual(candidate["canonical_url"], source)
        self.assertEqual(candidate["arxiv_id_version"], BASE + "v2")

    def test_wrong_exact_version_atom_does_not_fetch_or_promote_html(self):
        fixture, _, _ = self.arxiv_fixture(returned="v1")
        with self.assertRaisesRegex(ValueError, "another selected version"):
            resolution.resolve(BASE + "v2", transport=fixture)
        self.assertEqual(len(fixture.calls), 1)

    def test_conflicting_official_authors_or_pdf_identity_fail_closed(self):
        for changes in ({"authors": [AUTHORS[0]]}, {"title": "Another title"}, {"pdf": "https://arxiv.org/pdf/2408.11111"}):
            fixture, source, captured = self.arxiv_fixture()
            values = {"pdf": "https://arxiv.org/pdf/" + BASE, "arxiv": BASE, **changes}
            fixture.routes[source] = response(citation(**values))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                resolution.resolve(BASE + "v2", transport=fixture)

    def test_missing_html_never_becomes_verified_metadata(self):
        fixture, source, _ = self.arxiv_fixture()
        fixture.routes[source] = response("<html>Temporarily unavailable</html>")
        with self.assertRaisesRegex(ValueError, "citation_title"):
            resolution.resolve(BASE + "v2", transport=fixture)

    def test_wrong_content_type_and_xml_entity_declaration_are_rejected(self):
        fixture, _, _ = self.arxiv_fixture()
        api = next(iter(fixture.routes))
        for body, media in [(atom(), "text/html"), ('<!DOCTYPE x [<!ENTITY y "text">]>' + atom(), "application/xml")]:
            fixture.routes[api] = response(body, media)
            with self.subTest(media=media), self.assertRaises(ValueError):
                resolution.resolve(BASE + "v2", transport=fixture)

    def test_publisher_metadata_and_exact_main_pdf_route_preserve_complete_authors(self):
        source = "https://proceedings.neurips.cc/paper_files/paper/2024/hash/" + "a" * 32 + "-Abstract-Conference.html"
        pdf = source.replace("/hash/", "/file/").replace("-Abstract-", "-Paper-").replace(".html", ".pdf")
        captured = citation(pdf=pdf, doi=DOI, year="2025/04/23")
        fixture = Fixture({source: response(captured)})
        candidate = resolution.resolve(source, transport=fixture)
        self.assertEqual(candidate["canonical_id"], "doi:" + DOI)
        self.assertEqual(candidate["conference_year"], 2024)
        self.assertEqual(candidate["year"], 2025)
        self.assertEqual(candidate["expected_version"], "publishedVersion")
        self.assertEqual(candidate["source_evidence"]["html"], captured)
        self.assertEqual(candidate["lawful_routes"][0]["url"], pdf)

    def test_doi_less_pmlr_can_link_its_own_official_pdf(self):
        source = "https://proceedings.mlr.press/v306/wang26gs.html"
        pdf = "https://proceedings.mlr.press/v306/wang26gs/wang26gs.pdf"
        candidate = resolution.resolve(source, transport=Fixture({source: response(citation(pdf=pdf, year="2026"))}))
        self.assertIsNone(candidate["doi"])
        self.assertEqual(candidate["canonical_id"], "url:" + source)
        self.assertEqual(candidate["lawful_routes"][0]["url"], pdf)

    def test_official_publisher_cannot_supply_cross_paper_or_arbitrary_pdf(self):
        source = "https://proceedings.mlr.press/v306/wang26gs.html"
        for pdf in ("https://example.org/paper.pdf", "https://proceedings.mlr.press/v306/other/other.pdf"):
            with self.subTest(pdf=pdf), self.assertRaisesRegex(ValueError, "selected paper"):
                resolution.resolve(source, transport=Fixture({source: response(citation(pdf=pdf))}))

    def test_cvf_policy_is_captured_and_version_is_accepted(self):
        source = "https://openaccess.thecvf.com/content/CVPR2024/html/Example_Method_CVPR_2024_paper.html"
        pdf = source.replace("/html/", "/papers/").replace(".html", ".pdf")
        policy_url = "https://openaccess.thecvf.com/CVPR2024"
        policy = "<html>These copies are identical to the accepted versions; final published version available on IEEE Xplore.</html>"
        fixture = Fixture({source: response(citation(pdf=pdf)), policy_url: response(policy)})
        candidate = resolution.resolve(source, transport=fixture)
        self.assertEqual(candidate["expected_version"], "acceptedVersion")
        self.assertEqual(candidate["source_evidence"]["policy_html"], policy)
        self.assertEqual(len(candidate["sources"]), 2)
        fixture.routes[policy_url] = response("<html>Public page without version policy.</html>")
        with self.assertRaisesRegex(ValueError, "policy"):
            resolution.resolve(source, transport=fixture)

    def test_crossref_full_names_and_organization_names_are_retained_without_pdf_routes(self):
        payload = {"message": {"DOI": DOI, "title": [TITLE], "author": [
            {"given": "Marius", "family": "Memmel"}, {"name": "Robotics Consortium"}],
            "issued": {"date-parts": [[2024]]}, "type": "journal-article",
            "link": [{"URL": "https://example.org/unverified.pdf"}]}}
        api = "https://api.crossref.org/works/10.9999%2Fsynthetic-a"
        raw = json.dumps(payload)
        fixture = Fixture({api: response(raw, "application/json")})
        candidate = resolution.resolve(DOI, transport=fixture)
        self.assertEqual(candidate["authors"], ["Marius Memmel", "Robotics Consortium"])
        self.assertEqual(candidate["lawful_routes"], [])
        self.assertNotIn("source_evidence", candidate)
        self.assertEqual(candidate["sources"][0]["sha256"], hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(len(fixture.calls), 1)

    def test_boolean_year_cannot_be_verified_doi_metadata(self):
        payload = {"message": {"DOI": DOI, "title": [TITLE], "author": [{"family": "Memmel"}],
                               "issued": {"date-parts": [[True]]}}}
        api = "https://api.crossref.org/works/10.9999%2Fsynthetic-a"
        with self.assertRaisesRegex(ValueError, "year"):
            resolution.resolve(DOI, transport=Fixture({api: response(json.dumps(payload), "application/json")}))

    def test_crossref_redirect_cannot_fetch_or_certify_another_endpoint(self):
        api = "https://api.crossref.org/works/10.9999%2Fsynthetic-a"
        for destination in ("https://untrusted.example/metadata", "https://api.crossref.org/works/10.9999%2Fother"):
            fixture = Fixture({api: discovery.Response(302, {"Location": destination}, b"")})
            with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, "exact Crossref endpoint"):
                resolution.resolve(DOI, transport=fixture)
            self.assertEqual([call[1] for call in fixture.calls], [api])

    def test_arxiv_api_and_versioned_html_redirects_stop_before_the_next_fetch(self):
        for target in ("api", "html"):
            fixture, source, _ = self.arxiv_fixture()
            api = next(iter(fixture.routes))
            redirecting = api if target == "api" else source
            # An altered query on the same export host is also a different
            # selected metadata identity and must never reach the transport.
            destination = api.replace("v2", "v1") if target == "api" else "https://untrusted.example/page"
            fixture.routes[redirecting] = discovery.Response(302, {"Location": destination}, b"")
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "selected exact source URL"):
                resolution.resolve(BASE + "v2", transport=fixture)
            expected = [api] if target == "api" else [api, source]
            self.assertEqual([call[1] for call in fixture.calls], expected)

    def test_official_publisher_and_policy_redirects_stop_before_the_next_fetch(self):
        source = "https://openaccess.thecvf.com/content/CVPR2024/html/Example_Method_CVPR_2024_paper.html"
        pdf = source.replace("/html/", "/papers/").replace(".html", ".pdf")
        policy = "https://openaccess.thecvf.com/CVPR2024"
        for target in (source, policy):
            fixture = Fixture({source: response(citation(pdf=pdf)),
                               policy: response("<html>identical to the accepted versions; final published version on IEEE Xplore.</html>")})
            fixture.routes[target] = discovery.Response(302, {"Location": "https://untrusted.example/page"}, b"")
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "selected exact source URL"):
                resolution.resolve(source, transport=fixture)
            expected = [source] if target == source else [source, policy]
            self.assertEqual([call[1] for call in fixture.calls], expected)

    def test_bom_response_hashes_and_decoded_html_hashes_have_distinct_scopes(self):
        fixture, arxiv_source, _ = self.arxiv_fixture()
        publisher_source = "https://proceedings.mlr.press/v306/wang26gs.html"
        publisher_pdf = "https://proceedings.mlr.press/v306/wang26gs/wang26gs.pdf"
        publisher = Fixture({publisher_source: response(citation(pdf=publisher_pdf, year="2026"))})
        for requested, source, transport in ((BASE + "v2", arxiv_source, fixture),
                                             (publisher_source, publisher_source, publisher)):
            for url, captured in list(transport.routes.items()):
                transport.routes[url] = discovery.Response(captured.status, captured.headers, b"\xef\xbb\xbf" + captured.body)
            candidate = resolution.resolve(requested, transport=transport)
            packet = candidate["source_evidence"]
            source_capture = next(item for item in candidate["sources"] if item["url"] == source)
            raw_digest = hashlib.sha256(transport.routes[source].body).hexdigest()
            html_digest = hashlib.sha256(packet["html"].encode("utf-8")).hexdigest()
            with self.subTest(requested=requested):
                self.assertEqual(source_capture["digest_scope"], "response_bytes")
                self.assertEqual(source_capture["response_sha256"], raw_digest)
                self.assertEqual(source_capture["sha256"], raw_digest)
                self.assertEqual(source_capture["text_sha256"], html_digest)
                self.assertEqual(packet["html_sha256"], html_digest)
                self.assertNotEqual(raw_digest, html_digest)
                self.assertFalse(packet["html"].startswith("\ufeff"))

    def test_malformed_title_or_incomplete_author_list_cannot_be_verified(self):
        original = {"DOI": DOI, "title": [TITLE], "author": [{"family": "Memmel"}],
                    "issued": {"date-parts": [[2024]]}}
        api = "https://api.crossref.org/works/10.9999%2Fsynthetic-a"
        for changes in ({"title": TITLE}, {"author": [{"family": "Memmel"}, {}]},
                        {"author": [{"given": 42, "family": "Memmel"}]}, {"author": ["Memmel"]}):
            fixture = Fixture({api: response(json.dumps({"message": {**original, **changes}}), "application/json")})
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                resolution.resolve(DOI, transport=fixture)


if __name__ == "__main__":
    unittest.main()
