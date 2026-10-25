# External candidates and intake

Discovery is a metadata operation. `discovery.search(query)` looks up each returned
DOI at its canonical Crossref endpoint, requires title, author and year, and emits
`VERIFIED_METADATA` candidates with source and retrieval time. That status confirms
metadata identity only. Titles never become identifiers. Exact DOI/version
duplicates collapse only when metadata agrees; related versions stay separate.

`acquisition.run(settings, candidates, selected=[...], enabled=True, email=...)`
requires an explicit selection and an external runtime. Its default is disabled.
The per-paper JSON records and hashed PDF artifacts live in `runtime/intake/`,
outside the Vault. Re-running checks metadata and artifact hashes. Papers run
serially using configured `acquisition.max_bytes` and `acquisition.interval`; an
unavailable route, invalid selected candidate or failed download leaves a recorded
partial state without preventing other selected papers from progressing.
Only Unpaywall publisher/repository OA routes are considered, with route version,
license and source preserved. No institutional login, proxy, cookies or session
material is accepted. HTTPS destinations and every redirect are checked; the live
transport pins a public DNS answer, validates TLS, and limits bytes and time.

The optional pypdf verifier parses the PDF and compares first-page identity before
the references with canonical title, author, year and DOI. A reference-section DOI
does not verify a paper. Its outcomes are `VERIFIED`, `PROBABLE`, `AMBIGUOUS`,
`SUPPLEMENT`, `WRONG` and `CORRUPTED`. Only `VERIFIED` is eligible for a separate
explicit import. This is conservative identity checking, not a scientific judgment
or a guarantee of content authenticity. Missing pypdf, scanned text, unusual
layouts and conflicting DOI text require review. No OCR or article interpretation
is performed. OA route version is provenance, not proof of the PDF's publication
version. The verifier also requires an explicit first-page preprint, accepted
manuscript or published/version-of-record label. Its observed version must agree
with the OA route and any `expected_version` on the candidate. Matching DOI/title
without such version evidence remains `PROBABLE`; version conflict is `AMBIGUOUS`.

An explicit `source_evidence` packet on an import candidate activates
`pdf_identity.verify_source_pdf()` instead of that first-page-only path. It binds
the actual PDF SHA-256 to captured official citation HTML, exact main-PDF URL,
complete author list, source date and PDF version imprint. Exact arXiv versions
require both the versioned landing and embedded PDF watermark. Proceedings use
their official paper identifier and first-page conference/proceedings imprint;
CVF copies require the PDF watermark and captured accepted-version policy.
Publication and conference dates remain separate, and a related arXiv DOI cannot
stand in for a DOI-less publication. Missing or contradictory evidence fails
closed; no fallback promotes a failed packet. These are agent bibliographic
checks, not human review or scientific entailment judgments.

For PMLR files acquired via the public GitHub contents API, an explicit alternate
acquisition URL additionally requires the exact officially linked repository
path, captured file metadata and a calculated Git blob identity matching the
downloaded bytes. An explicitly recorded additional-middle-name variant is
allowed only when the official first/last name agrees, the full form is printed
in the first-page author block, and all other source/version checks still pass.
Both names remain in the verdict; general fuzzy author matching is not used.
PDF extraction uses the optional `pdf` dependencies, including fontTools for CFF
fonts. An extraction warning or skipped form content remains an explicit reading
limit; successful identity verification does not certify complete extraction.

## Zotero boundary

`zotero.Client('users/0')` targets the explicit loopback Local API.
`inventory()` reads all pages including attachments and rejects changed library
versions, changed server identity or incomplete pages. `find_pdf()` returns
parent/attachment metadata without modifying or opening local files. Explicit
keys never fall back to a DOI or title search. All identities include a library;
cached local identity also includes the Zotero Server ID.

`create_item()` and `import_pdf()` default to a plan. Actual writes require
`apply=True`, an environment key named `ZOTERO_API_KEY`, a fresh durable receipt
path, complete inventory, and a Zotero 10+ Server ID.
The adapter does not persist keys. A caller may use the operating system's
protected credential store when the user explicitly requests retention, exposing
the key only through the current process environment. No key belongs in YAML,
ordinary files, receipts or logs.
The adapter uses standard new-item POST and conditional full-file upload, then
reads back item/file metadata. It never updates, replaces or deletes existing
items, PDFs or annotations. Existing PDFs stop an import. The caller must keep
receipts outside the Vault and repository, retain them across runs, and use the
same receipt for the same intended operation. Before every POST the receipt is
flushed and fsynced and an optional persistence callback is invoked. Uncertain
outcomes become `MANUAL_RECONCILIATION_REQUIRED`; an existing receipt blocks
automatic resubmission. A fresh filename is not permission to bypass reconciliation.

The Local API does not expose the Web API's `/items/new` convenience route.
Creation therefore submits editable metadata with the documented `itemType`,
`tags`, `collections` and `relations` containers; Zotero validates item-specific
fields. Inventory uses supported `dateAdded` sorting with version consistency.
Normal API responses require the same Server ID. The upload-key-authorized byte
endpoint may omit that header, while a conflicting supplied ID still fails.
HTTP failures retain their actual status instead of becoming missing-ID errors.

DOI-less parents may use exact canonical PMLR volume/slug, NeurIPS/ICLR paper
hash or CVF paper routes. Arbitrary URLs and titles are not stable identities.
Duplicate/conflicting DOI or publisher identity stops creation; DOI-less imports
also require the selected canonical publisher identity to match the read-back
parent. `--receipt` in the CLI is relative to configured external `runtime_dir`,
with absolute paths, traversal and resolved link escapes rejected before API use.

The adapter does not request local authorization or handle authorization dialogs.
Provide a remembered local key through the environment after user authorization;
single-use keys may expire during the multi-request upload, requiring manual
reconciliation. Local keys and Web API keys are different. Web API transport,
SQLite access, linked-file copying and live-data acceptance are out of scope for
phase one. The fixtures exercise the official request sequence without a running
Zotero instance. Real client interoperability remains for the explicitly continued
read-only validation stage.

## Official contracts consulted

The implementation was written independently against these official pages,
checked on 2026-09-26 and 2026-09-27. No third-party client implementation was used.

- [Zotero Local API](https://www.zotero.org/support/dev/web_api/v3/local_api):
  local origin, Server ID, versions and Zotero 10+ write/upload support.
- [Zotero API basics](https://www.zotero.org/support/dev/web_api/v3/basics):
  namespaced libraries, item envelopes, total counts and pagination.
- [Zotero write requests](https://www.zotero.org/support/dev/web_api/v3/write_requests):
  item templates, create arrays, optimistic preconditions and returned keys.
- [Zotero file uploads](https://www.zotero.org/support/dev/web_api/v3/file_upload):
  attachment creation, conditional authorization, upload and registration.
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/):
  works search and canonical DOI metadata.
- [Unpaywall API](https://data.unpaywall.org/products/api): DOI endpoint and
  required email. Its former search endpoint retired on 2026-09-18; this project
  uses Crossref for search and only DOI lookup for Unpaywall.
- [Unpaywall data format](https://unpaywall.org/data-format): location URLs,
  host type, license and submitted/accepted/published version metadata.

## Deliberate limits

This first adapter handles Crossref DOI candidates, one first eligible OA route
per attempt and local Zotero libraries. It does not silently infer arXiv/DOI
equivalence, chase citations, discover credentials, fall back to title identities,
or fabricate missing metadata. HTTP failures are not blindly retried. State and
receipts provide application-level crash evidence; they are not trusted timestamps
or an exactly-once guarantee against concurrent independent clients. A successful
unit test is synthetic protocol evidence, not proof of live interoperability.
