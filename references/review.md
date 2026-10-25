# Systematic review evidence

A review records a bounded search process. It does not certify that the external
literature is exhausted. Paper counts and percentages are not completion gates.
The one Corpus YAML file separates screening and search records from the human
review narrative.

## Protocol and execution records

A `review-protocol` has `review_id`, `version`, `scope`, prior
`inclusion_criteria` and `exclusion_criteria`, `sources`, `seed_papers`,
`query_families`, `citation_policy` and `corpus_path`. Each family has a distinct
`family_id`, a `purpose` and a list of planned `queries`. The citation policy
contains `max_rounds` and `directions` (`backward`, `forward`).

The corpus has `schema_version: 2`, the same `review_id`, `protocol_version`,
and these collections:

| Field | Recorded content |
| --- | --- |
| `searches` | `family_id`, actual `query`, `source`, ISO `executed_at`, `returned_ids` |
| `papers` | canonical `paper_id`, `decision` (`include`, `exclude`, `pending`), explicit `reason` |
| `deduplication` | Boolean `performed`, `method`, and `duplicates` entries with `kept`, `removed`, `reason` |
| `citation_rounds` | `direction`, bounded integer `round`, `seed_ids`, `found_ids`, `executed_at` |
| `challenges` | `type`, actual `query`, `source`, `executed_at`, `found_ids` |
| `coverage` | nonempty `dimensions` mapping, explicit `limits`, `unsearched` list |
| `evidence_matrix` | distinct included `paper_id`, `note_path`, `position`, `finding`, Boolean `critical` |

Paper identities use `doi:<identifier>`, `arxiv:<identifier>` or
`zotero:user:local:<parent-key>` / `zotero:group:<library-id>:<parent-key>`.
Titles never substitute for those identifiers. Every discovered candidate has a
screening decision or an explicit duplicate decision. Every corpus paper has
seed, query or citation provenance. Pending papers remain visible.

Actual search strings must match their prior family definitions. Changes to the
search design require a protocol revision. Citation rounds cannot exceed the
declared bound. Supporting, competing, contradictory, null and
alternative-mechanism challenges are independent query types. One copied query
with five labels does not satisfy the external review gate.

## Corpus Freeze

`review.freeze(settings, path, apply=False, previous=None, reason=None)` returns
the digest, receipt path and proposed `corpus_digest` / `corpus_receipt` metadata.
It freezes the protocol definitions and the entire corpus, including screening,
included identities, search provenance and coverage. `apply=True` creates the
receipt without modifying the human page. Apply proposed metadata as a reviewed
page edit.

The receipt uses the same canonical JSON and history rules as scientific locks.
A changed corpus needs a changed protocol version, the latest `previous` digest
and a nonempty revision `reason`. A newly found paper cannot silently enter a
frozen corpus. Removing the page reference does not reset its history.

## Gap gate and critical evidence

A `research-gap` marked `review_status: externally_checked` binds `review_id`
and `corpus_digest` to a valid frozen protocol. It requires distinct actually
executed query families, completed deduplication, all five distinct challenge
query types, resolved screening decisions and recorded coverage limits. Missing
citation work must be disclosed in `coverage.unsearched`. This is process
evidence, not a claim that the gap is scientifically established.

`confidence: high` additionally requires `evidence_ids` naming critical included
evidence-matrix rows. Each row resolves to the actual `literature-note` for that
canonical publication and declares `evidence_status: fulltext_verified` or
`pdf_verified`. Its `verification` list uses the shared source-verification
contract: `fulltext_path`, `zotero_key`, `pdf_key`, an exact `quote` when cited,
and `pdf_path` / `locator.pdf_page` for direct PDF evidence. The common evidence
validator checks actual source availability, identity links, quoted text and
page bounds. A trusted-looking label by itself cannot open the high-confidence
gate. These checks do not infer entailment or substitute for human reading.
