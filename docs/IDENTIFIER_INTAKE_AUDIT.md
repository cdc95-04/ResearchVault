# Identifier intake architecture and boundaries

This document maps the existing implementation and its evidence obligations.
It is not a private worktree audit or a live-service acceptance report. The
workflow coordinates an explicitly selected DOI, exact arXiv version or supported
paper URL into metadata, lawful PDF evidence, Zotero identity, Fulltext and a
partial Paper Note. It does not perform new literature discovery.

## Reused components

| Component | Responsibility | Boundary |
| --- | --- | --- |
| [Identity](../researchvault/identity.py) | Normalize and compare publication identifiers | Publication identity, library namespace, parent and attachment keys remain distinct |
| [Resolution](../researchvault/resolution.py) | Parse selected input and capture canonical metadata/version evidence | No arbitrary-page crawler or title-only identity proof |
| [Discovery transport](../researchvault/discovery.py) | Bounded public HTTPS requests and official source lookup | Reject private destinations, credential-bearing URLs and unsafe redirects |
| [Acquisition](../researchvault/acquisition.py) | Lawful OA route discovery and bounded PDF handling | Explicit authorization, source provenance and resumable per-item outcomes |
| [PDF identity](../researchvault/pdf_identity.py) | Compare actual bytes with official metadata/version evidence | Failed explicit source evidence cannot fall back to a weaker verifier |
| [Zotero](../researchvault/zotero.py) | Inventory, exact PDF reads, create-only parent/attachment workflow | Official Local API, instance checks, durable intent and independent read-back |
| [Fulltext](../researchvault/fulltext.py) | Preserve original extraction and provenance | Existing conflicting source evidence is not overwritten |
| [Note formatter](../researchvault/notes.py) | Render source-labelled draft Notes from supplied inputs | No automatic scientific inference or human approval |
| [Coordinator](../researchvault/intake.py) | Persist selected-item state and connect existing stages | No unrestricted retry, hidden policy change or global transaction guarantee |
| [Document publication](../researchvault/documents.py) | Create-only record and staged-byte handling | Existing records and competing writers remain protected |
| [Validation](../researchvault/validation.py) | Identity, links, hashes, excerpts and structural contracts | Does not certify semantic entailment or equation fidelity |
| [Configuration](../researchvault/config.py) | Explicit roots, containment and read-only policy | Repository, Vault, runtime and source evidence remain separate |

The existing Skills retain their responsibilities: [ingest-orchestrator](../skills/ingest-orchestrator/SKILL.md)
coordinates the selected batch, [zotero-fetcher](../skills/zotero-fetcher/SKILL.md)
reads identity, [fulltext-archiver](../skills/fulltext-archiver/SKILL.md) preserves
text, and [paper-note-writer](../skills/paper-note-writer/SKILL.md) performs
scientific reading. The coordinator does not create another Skill family.

## Identity before mutation

The selected batch is bounded by explicit input. DOI aliases normalize together;
exact arXiv versions remain distinct. Related publisher and preprint versions,
accepted manuscripts and supplements are not silently merged. Titles are hints
and conflict checks, not stable deduplication keys.

The complete inventory checks pagination, library version and Server ID before
planning creation. Multiple plausible parents or attachments require resolution.
An existing PDF is obtained through the official file-URI endpoint; remote shares
and remote URLs are rejected. Bytes are checked against inventory MD5 and hashed
with SHA-256. The client does not infer Zotero storage locations or read SQLite.

Explicit source packets bind official responses, version imprints and actual
PDF bytes. A DOI match alone does not establish the selected publication version,
main-document role or scientific validity. Wrong, ambiguous, supplementary and
corrupt PDFs cannot reach automatic attachment import.

## External write and resume boundaries

Zotero parent creation and attachment upload use durable intents persisted before
mutation. Completion requires read-back. An uncertain result retains its receipt
and requires reconciliation; a new filename, process or identifier alias cannot
authorize blind resubmission. Namespace and Server ID must agree on resume.

Runtime candidate captures are frozen. Resume uses the same metadata/version and
hashes instead of discovering a newer source. Its exclusive local workflow lock
prevents overlapping operations through that runtime, but does not create an
exactly-once guarantee across independent clients.

Missing credentials and unavailable services stop the affected operation. The
coordinator never requests an authorization dialog, changes protected credential
storage, edits global policy or accesses `zotero.sqlite`.

## Archive publication and existing records

Before reuse, Fulltext and Note must agree on library, parent, attachment, source
hashes and reciprocal paths. Scan exact identities across the selected Vault;
checking only a prospective filename is insufficient. Existing user edits are a
conflict to preserve, not permission to regenerate the record.

New pair bytes are staged and hash-bound, flushed, then published create-only
using same-volume hard links. Unsupported filesystems fail closed. Resume may
publish a missing counterpart from the original staged bytes but must not
replace an occupied path. This is recoverable publication, not an atomic
transaction spanning the filesystem and Zotero.

## Scientific evidence boundary

The automatic Note uses the existing [seventeen-section template](../templates/paper.md)
and [reading checks](../references/reading.md). It remains draft, partial,
unverified and human pending. Without an analysis capture, completion reports
`ARCHIVED_ANALYSIS_PENDING` and creates an explicit handoff to paper-note-writer.

An optional capture binds the PDF SHA-256, a one-based extraction page and a
literal quote. Normalized quote matching checks text presence only. It does not
prove entailment, printed page numbering, mathematical transcription or visible
figure content. Paraphrases remain interpretations and untested ideas remain
speculative. A new capture does not silently rewrite an existing Note on resume.

The formatter keeps untrusted metadata and prose literal while separately
generating authorized navigation. Original extraction remains unchanged in
Fulltext. See [archive quality](PHASE1_1_ARCHIVE_QUALITY.md) for escaping and NUL
handling rather than applying lossy cleanup to evidence.

## Verification obligations

[Automated coverage](IDENTIFIER_INTAKE_RESULTS.md) exercises offline preview,
guards, source identity, selected-item failures, create-only receipts, conflicts,
partial publication and resume with synthetic transports. [Real acceptance](PHASE1_REAL_ACCEPTANCE.md)
requires separately recorded actual services, source bytes, independent read-back
and hash agreement. Neither kind of check supplies human scientific approval.
