"""Observed intake failures: DOI-less proceedings and explicit arXiv versions."""
import hashlib
import html
import importlib.util
import io
import unittest

from researchvault.pdf_identity import verify_source_pdf


def citation_html(title, authors, pdf_url, year="2024", doi="10.52202/example", **extra):
    values = [("citation_title", title), *(("citation_author", author) for author in authors),
              ("citation_publication_date", year), ("citation_pdf_url", pdf_url)]
    if doi:
        values.append(("citation_doi", doi))
    values.extend(extra.items())
    return "<html><head>" + "".join(
        f'<meta content="{html.escape(value, quote=True)}" name="{key}">' for key, value in values
    ) + "</head></html>"


def pdf_bytes(lines):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = DecodedStreamObject()
    stream.set_data(("BT /F1 12 Tf 15 760 Td " + " 0 -20 Td ".join(f"({line}) Tj" for line in escaped) + " ET").encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO(); writer.write(buffer)
    return buffer.getvalue()


@unittest.skipUnless(importlib.util.find_spec("pypdf"), "Optional pypdf required")
class SourceBoundPdfIdentity(unittest.TestCase):
    def setUp(self):
        self.title = "Active Exploration for System Identification"
        self.authors = ["Marius Memmel", "Andrew Wagenmaker"]
        self.source = "https://proceedings.neurips.cc/paper_files/paper/2024/hash/" + "a" * 32 + "-Abstract-Conference.html"
        self.pdf_url = self.source.replace("/hash/", "/file/").replace("-Abstract-", "-Paper-").replace(".html", ".pdf")
        self.lines = [self.title, ", ".join(self.authors), "Abstract", "Study text.",
                      "38th Conference on Neural Information Processing Systems (NeurIPS 2024)."]
        self.content = pdf_bytes(self.lines)
        self.candidate = {"title": self.title, "authors": self.authors, "year": 2024,
                          "doi": "10.52202/example", "expected_version": "publishedVersion"}
        self.evidence = self.packet(self.content, self.source, self.pdf_url, "publishedVersion")

    def packet(self, content, source, pdf_url, version, **extra):
        return {"source_url": source, "pdf_url": pdf_url, "version": version,
                "html": citation_html(self.title, self.authors, pdf_url),
                "retrieved_at": "2026-10-07T08:00:00+00:00",
                "sha256": hashlib.sha256(content).hexdigest(), **extra}

    def verify(self, content=None, candidate=None, evidence=None):
        return verify_source_pdf(self.content if content is None else content,
                                 self.candidate if candidate is None else candidate,
                                 self.evidence if evidence is None else evidence)

    def changed_pdf(self, lines):
        content = pdf_bytes(lines)
        return content, {**self.evidence, "sha256": hashlib.sha256(content).hexdigest()}

    def test_official_proceedings_without_printed_doi_use_source_doi_and_imprint(self):
        verdict = self.verify()
        self.assertEqual(verdict["status"], "VERIFIED")
        self.assertTrue(all(verdict["checks"].values()))
        self.assertEqual(verdict["source_anchor"]["doi"], "10.52202/example")

    def test_wrong_artifact_hash_fails_before_identity_promotion(self):
        self.assertEqual(self.verify(evidence={**self.evidence, "sha256": "0" * 64})["status"], "WRONG")

    def test_changed_capture_cannot_keep_its_old_html_digest(self):
        evidence = {**self.evidence, "html_sha256": "0" * 64}
        self.assertEqual(self.verify(evidence=evidence)["status"], "WRONG")

    def test_alternate_github_acquisition_must_bind_exact_blob_and_publisher_link(self):
        source = "https://proceedings.mlr.press/v306/example26a.html"
        pdf_url = "https://raw.githubusercontent.com/mlresearch/v306/main/assets/example26a/example26a.pdf"
        api = "https://api.github.com/repos/mlresearch/v306/contents/assets/example26a/example26a.pdf?ref=main"
        content = pdf_bytes([self.title, ", ".join(self.authors), "Abstract", "Study text.", "Proceedings of the 43rd International Conference on Machine Learning, PMLR 306, 2026."])
        evidence = self.packet(content, source, pdf_url, "publishedVersion")
        evidence.update(html=citation_html(self.title,self.authors,pdf_url,year="2026",doi=None), acquisition_url=api, repository_metadata_url=api, repository_retrieved_at=evidence["retrieved_at"], repository_file={"type":"file", "path":"assets/example26a/example26a.pdf", "size":len(content), "download_url":pdf_url, "sha":hashlib.sha1(b"blob "+str(len(content)).encode()+b"\0"+content,usedforsecurity=False).hexdigest()})
        candidate = {**self.candidate, "doi":None, "year":2026}
        self.assertEqual(self.verify(content=content,candidate=candidate,evidence=evidence)["status"], "VERIFIED")
        for change in ({"sha":"0"*40},{"path":"assets/other/other.pdf"},{"download_url":pdf_url.replace("example26a", "other")}):
            invalid={**evidence,"repository_file":{**evidence["repository_file"],**change}}
            with self.subTest(change=change):
                self.assertEqual(self.verify(content=content,candidate=candidate,evidence=invalid)["status"], "WRONG")

    def test_absent_capture_and_absent_hash_fail_closed(self):
        for key in ("html", "sha256", "retrieved_at"):
            evidence = {name: value for name, value in self.evidence.items() if name != key}
            with self.subTest(key=key):
                self.assertEqual(self.verify(evidence=evidence)["status"], "AMBIGUOUS")

    def test_wrong_source_doi_cannot_be_replaced_by_title_match(self):
        evidence = {**self.evidence, "html": citation_html(self.title, self.authors, self.pdf_url, doi="10.9999/other")}
        self.assertEqual(self.verify(evidence=evidence)["status"], "WRONG")

    def test_publication_without_doi_does_not_substantiate_an_arxiv_doi(self):
        evidence = {**self.evidence, "html": citation_html(self.title, self.authors, self.pdf_url, doi=None)}
        self.assertEqual(self.verify(evidence=evidence)["status"], "AMBIGUOUS")

    def test_wrong_pdf_title_and_longer_title_are_rejected(self):
        for title in ("Another Paper", self.title + " Extended"):
            content, evidence = self.changed_pdf([title, *self.lines[1:]])
            with self.subTest(title=title):
                self.assertEqual(self.verify(content=content, evidence=evidence)["status"], "WRONG")

    def test_title_cited_in_abstract_is_not_document_identity(self):
        content, evidence = self.changed_pdf(["Another Paper", self.lines[1], "Abstract", self.title, self.lines[-1]])
        self.assertEqual(self.verify(content=content, evidence=evidence)["status"], "WRONG")

    def test_each_pdf_author_is_required(self):
        content, evidence = self.changed_pdf([self.title, self.authors[0], *self.lines[2:]])
        self.assertEqual(self.verify(content=content, evidence=evidence)["status"], "WRONG")

    def test_explicit_printed_middle_name_preserves_source_and_pdf_forms(self):
        content,evidence=self.changed_pdf([self.title,"Marius Jin Memmel, Andrew Wagenmaker",*self.lines[2:]])
        self.assertEqual(self.verify(content=content,evidence=evidence)["status"],"WRONG")
        variant={"source_name":"Marius Memmel","pdf_name":"Marius Jin Memmel","page":1,"kind":"additional_middle_names"}
        evidence={**evidence,"author_name_variants":[variant]}
        verdict=self.verify(content=content,evidence=evidence)
        self.assertEqual(verdict["status"],"VERIFIED")
        self.assertEqual(verdict["source_anchor"]["author_name_variants"],[variant])
        for change in ({"pdf_name":"Marius Jin Other"},{"pdf_name":"M. Jin Memmel"},{"page":2},{"source_name":"Unknown Memmel"},{"pdf_name":"Marius Unprinted Memmel"}):
            with self.subTest(change=change):
                invalid={**evidence,"author_name_variants":[{**variant,**change}]}
                self.assertEqual(self.verify(content=content,evidence=invalid)["status"],"AMBIGUOUS")
        self.assertEqual(self.verify(content=content,evidence={**evidence,"author_name_variants":[variant,variant]})["status"],"AMBIGUOUS")

    def test_publication_author_list_must_not_merge_another_version(self):
        candidate = {**self.candidate, "authors": self.authors + ["Patrick Yin"]}
        self.assertEqual(self.verify(candidate=candidate)["status"], "WRONG")

    def test_citation_authors_support_last_first_format(self):
        evidence = {**self.evidence, "html": citation_html(self.title, ["Memmel, Marius", "Wagenmaker, Andrew"], self.pdf_url)}
        self.assertEqual(self.verify(evidence=evidence)["status"], "VERIFIED")

    def test_official_link_to_different_paper_cannot_verify_acquired_bytes(self):
        evidence = {**self.evidence, "html": citation_html(self.title, self.authors, self.pdf_url.replace("a" * 32, "b" * 32))}
        self.assertEqual(self.verify(evidence=evidence)["status"], "WRONG")

    def test_untrusted_source_and_cross_paper_acquisition_url_are_rejected(self):
        self.assertEqual(self.verify(evidence={**self.evidence, "source_url": self.source.replace("proceedings.neurips.cc", "example.org")})["status"], "AMBIGUOUS")
        self.assertEqual(self.verify(evidence={**self.evidence, "pdf_url": self.pdf_url.replace("a" * 32, "b" * 32)})["status"], "WRONG")

    def test_supplement_heading_prevents_main_paper_intake(self):
        content, evidence = self.changed_pdf(["Supplementary Material", *self.lines])
        self.assertEqual(self.verify(content=content, evidence=evidence)["status"], "SUPPLEMENT")

    def test_corrupted_pdf_and_missing_embedded_imprint_fail_closed(self):
        self.assertEqual(self.verify(content=b"%PDF-invalid")["status"], "CORRUPTED")
        content, evidence = self.changed_pdf(self.lines[:-1])
        self.assertEqual(self.verify(content=content, evidence=evidence)["status"], "AMBIGUOUS")

    def test_conflicting_official_dois_require_review(self):
        evidence = {**self.evidence, "html": self.evidence["html"] + '<meta name="citation_doi" content="10.9999/other">'}
        self.assertEqual(self.verify(evidence=evidence)["status"], "AMBIGUOUS")

    def test_first_page_primary_doi_cannot_conflict_with_official_source(self):
        content, evidence = self.changed_pdf([*self.lines[:2], "DOI: 10.9999/other", *self.lines[2:]])
        self.assertEqual(self.verify(content=content, evidence=evidence)["status"], "WRONG")

    def test_neurips_conference_year_can_differ_from_electronic_publication_year(self):
        candidate = {**self.candidate, "year": 2025, "conference_year": 2024}
        evidence = {**self.evidence, "html": citation_html(self.title, self.authors, self.pdf_url, year="2025-04-23")}
        self.assertEqual(self.verify(candidate=candidate, evidence=evidence)["status"], "VERIFIED")
        self.assertEqual(self.verify(evidence=evidence)["status"], "WRONG")

    def test_iclr_split_small_caps_and_line_hyphenation_preserve_exact_identity(self):
        source = self.source.replace("proceedings.neurips.cc", "proceedings.iclr.cc")
        url = self.pdf_url.replace("proceedings.neurips.cc", "proceedings.iclr.cc")
        content = pdf_bytes(["Published as a conference paper at ICLR 2024", "A CTIVE EXPLORATION FOR SYSTEM IDENTIFI -", "CATION", self.lines[1], "Abstract", "Study."])
        evidence = self.packet(content, source, url, "publishedVersion", html=citation_html(self.title, self.authors, url, doi=None))
        self.assertEqual(self.verify(content=content, candidate={**self.candidate, "doi": None}, evidence=evidence)["status"], "VERIFIED")

    def test_doi_less_pmlr_publication_has_distinct_proceedings_identity(self):
        source = "https://proceedings.mlr.press/v306/wang26gs.html"
        url = "https://raw.githubusercontent.com/mlresearch/v306/main/assets/wang26gs/wang26gs.pdf"
        content = pdf_bytes([*self.lines[:-1], "Proceedings of the 43rd International Conference on Machine Learning, Seoul. PMLR 306, 2026."])
        evidence = self.packet(content, source, url, "publishedVersion", html=citation_html(self.title, self.authors, url, year="2026/09/29", doi=None))
        verdict = self.verify(content=content, candidate={**self.candidate, "doi": None, "year": 2026}, evidence=evidence)
        self.assertEqual(verdict["status"], "VERIFIED")
        self.assertNotIn("doi", verdict["source_anchor"])

    def test_pmlr_official_direct_pdf_is_bound_to_exact_volume_and_paper_stem(self):
        source = "https://proceedings.mlr.press/v306/wang26gs.html"
        url = "https://proceedings.mlr.press/v306/wang26gs/wang26gs.pdf"
        content = pdf_bytes([*self.lines[:-1], "Proceedings of the 43rd International Conference on Machine Learning, Seoul. PMLR 306, 2026."])
        candidate = {**self.candidate, "doi": None, "year": 2026}
        evidence = self.packet(content, source, url, "publishedVersion",
                               html=citation_html(self.title, self.authors, url, year="2026/09/29", doi=None))
        verdict = self.verify(content=content, candidate=candidate, evidence=evidence)
        self.assertEqual(verdict["status"], "VERIFIED")
        self.assertTrue(verdict["checks"]["official_pdf_destination"])
        self.assertEqual(verdict["source_anchor"]["pdf_url"], url)

        for other in (url.replace("/v306/", "/v305/"),
                      url.replace("/wang26gs/", "/other26a/"),
                      url.replace("wang26gs.pdf", "other26a.pdf"),
                      url.replace("proceedings.mlr.press", "example.org")):
            changed = {**evidence, "pdf_url": other,
                       "html": citation_html(self.title, self.authors, other, year="2026/09/29", doi=None)}
            with self.subTest(url=other):
                verdict = self.verify(content=content, candidate=candidate, evidence=changed)
                self.assertEqual(verdict["status"], "WRONG")
                self.assertFalse(verdict["checks"]["official_pdf_destination"])

    def arxiv_packet(self, embedded="2408.06316v1"):
        arxiv = "2408.06316v1"
        source = "https://arxiv.org/abs/" + arxiv
        url = "https://arxiv.org/pdf/" + arxiv
        content = pdf_bytes([*self.lines[:-1], "arXiv:" + embedded + " [cs.RO] 12 Aug 2024"])
        evidence = self.packet(content, source, url, "arxiv:" + arxiv,
                               html=citation_html(self.title, self.authors, "https://arxiv.org/pdf/2408.06316", doi=None,
                                                  citation_arxiv_id="2408.06316", citation_online_date="2024/08/12"))
        candidate = {**self.candidate, "doi": "10.48550/arXiv.2408.06316", "arxiv_id_version": arxiv, "expected_version": "arxiv:" + arxiv}
        return content, candidate, evidence

    def test_exact_arxiv_page_and_watermark_verify_version_without_printed_doi(self):
        content, candidate, evidence = self.arxiv_packet()
        self.assertEqual(self.verify(content, candidate, evidence)["status"], "VERIFIED")

    def test_wrong_arxiv_watermark_version_cannot_use_right_work_title(self):
        content, candidate, evidence = self.arxiv_packet("2408.06316v2")
        self.assertEqual(self.verify(content, candidate, evidence)["status"], "WRONG")

    def test_unversioned_arxiv_landing_does_not_prove_selected_version(self):
        content, candidate, evidence = self.arxiv_packet()
        evidence["source_url"] = "https://arxiv.org/abs/2408.06316"
        self.assertEqual(self.verify(content, candidate, evidence)["status"], "AMBIGUOUS")

    def test_arxiv_version_cannot_claim_publication_doi(self):
        content, candidate, evidence = self.arxiv_packet()
        candidate["doi"] = "10.9999/journal"
        self.assertEqual(self.verify(content, candidate, evidence)["status"], "WRONG")

    def cvf_packet(self):
        source = "https://openaccess.thecvf.com/content/CVPR2024/html/Liang_Rapid_Motor_Adaptation_CVPR_2024_paper.html"
        url = source.replace("/html/", "/papers/").replace(".html", ".pdf")
        policy = "These CVPR 2024 papers are Open Access versions. Except for the watermark, they are identical to the accepted versions; the final published version of the proceedings is available on IEEE Xplore."
        content = pdf_bytes([*self.lines[:-1], "This CVPR paper is the Open Access version, provided by the Computer Vision Foundation.", "Except for this watermark, it is identical to the accepted version;", "the final published version of the proceedings is available on IEEE Xplore."])
        evidence = self.packet(content, source, url, "acceptedVersion",
                               html=citation_html(self.title, self.authors, url, doi=None),
                               policy_url="https://openaccess.thecvf.com/CVPR2024", policy_html=policy,
                               policy_retrieved_at="2026-10-07T08:00:00+00:00")
        candidate = {**self.candidate, "doi": None, "expected_version": "acceptedVersion"}
        return content, candidate, evidence

    def test_cvf_watermark_and_official_policy_verify_accepted_copy(self):
        content, candidate, evidence = self.cvf_packet()
        self.assertEqual(self.verify(content, candidate, evidence)["status"], "VERIFIED")

    def test_cvf_copy_cannot_be_silently_labelled_final_published_version(self):
        content, candidate, evidence = self.cvf_packet()
        evidence["version"] = candidate["expected_version"] = "publishedVersion"
        self.assertEqual(self.verify(content, candidate, evidence)["status"], "AMBIGUOUS")

    def test_cvf_policy_is_required_separately_from_acquisition_route_label(self):
        content, candidate, evidence = self.cvf_packet()
        evidence.pop("policy_html")
        self.assertEqual(self.verify(content, candidate, evidence)["status"], "AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()
