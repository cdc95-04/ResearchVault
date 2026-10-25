# C0 independent static architecture audit

Status: **completed**. Baseline:
`2ec9afeb1f591c1bab41ad173f04c85cda4df5ab`.
This file records the independent C0 conclusions supplied in the owner's C1a
continuation instructions. Baseline inventory was also verified against tracked
repository files. This is static evidence, not a new private-library inspection,
human Golden approval or demonstration of actual research use.

| Baseline inventory | Count |
| --- | ---: |
| Tracked files | 147 |
| Canonical Skills | 12 |
| Shared references | 5 |
| Canonical templates | 22 |
| researchvault Python modules | 16 |

These counts describe the pinned C0 baseline, not a changing current-file quota.
The preceding [B2 evidence](SEMANTIC_RETRIEVAL_EVALUATION.md) remains a
separate historical record. The baseline CI record is retained in the private
development repository and is not publicly accessible. It is not evidence for
this release; current checks run through the release repository's
[CI workflow](../.github/workflows/ci.yml).

## Skill boundaries: all KEEP

| Canonical Skill | Decision | Boundary retained |
| --- | --- | --- |
| literature-discovery | KEEP AS-IS | External candidates and metadata |
| literature-acquisition | KEEP AS-IS | Selected lawful acquisition and identity checks |
| systematic-literature-review | KEEP AS-IS | Protocol, screening, challenge searches and Corpus Freeze |
| zotero-fetcher | KEEP AS-IS | Existing library parent/attachment reads |
| fulltext-archiver | KEEP AS-IS | Original source storage |
| paper-note-writer | KEEP AS-IS | Single-paper interpretation |
| knowledge-maintainer | KEEP AS-IS | Source-bound cross-paper synthesis |
| literature-retrieval | KEEP AS-IS | Local interpretation, expansion and evidence verification |
| research-maintainer | KEEP AS-IS | Research objects and Claim Lock |
| experiment-manager | KEEP AS-IS | Design Lock, Trials and Results |
| writing-support | KEEP AS-IS | Writing evidence and Claim Ledger |
| ingest-orchestrator | KEEP AS-IS | Explicit bounded batch coordination |

`ingest-orchestrator` is not currently a God Skill. It coordinates a selected
batch, reads the intake reference and loads another Skill only when its stage is
needed. It routes existing-library reads, source archiving and paper analysis;
it neither expands the batch silently nor invents analytical Notes. Its broader
workflow role is distinct from the Python CLI's selected batch archive operation.

Context loading already follows progressive disclosure: one relevant Skill,
then its required references/templates. Keep the five separate evidence,
science, review, intake and reading references. Combining them into one document
would require unrelated contracts to be loaded together.

## Objects, evidence and artifact footprint

Scientific objects, stable IDs, schema 2, evidence labels and experimental
verdicts retain their distinct meanings. Claim Lock, Design Lock and Corpus
Freeze bind different decisions; their receipts and revision histories are
integrity evidence. Trial files preserve every attempt. These artifacts are not
accidental maintenance complexity and are not deletion candidates.

No user-workflow artifact explosion was found. Ordinary Paper Notes and Knowledge
do not require a receipt for each operation; important provenance and specialized
freezes are explicit. The larger B2 cases/captures/results collection is benchmark
audit evidence, not the default research workflow. Preserve it byte-for-byte.

Deterministic validation, semantic evaluation and human review must stay separate.
The small retrieval benchmark gives no evidence for embeddings or a vector DB.
No new source inspection or human decision is inferred from this static audit.

## Maintenance concentration and allowed C1a work

The actionable accidental complexity is concentrated in maintenance/evaluation
infrastructure rather than scientific behavior:

| Finding | Low-risk treatment | Boundary |
| --- | --- | --- |
| Repeated JSON, digest, path and frozen-input mechanics | Minimal shared scripts helper | Preserve Golden, semantic and retrieval meanings |
| Scripts acting as libraries for sibling scripts | Share mechanical inputs/mappings directly | No evaluator framework or runtime harness |
| Duplicated release values and unused config preferences | One package-version source; confirm consumers before removal | Vault schema remains independent |
| CLI ingest name covers a narrower Python operation | Retain compatibility and clarify source-archive help | No autonomous orchestration or Note generation |
| Repository audit repeats installed dependency existence/version checks | Delegate dependency invariants to existing install/check/audit gates | Retain hygiene, links, templates and license checks |
| README repeats historical benchmark metrics | Link canonical evidence reports | Historical measurements remain unchanged |

`process.py` and `review.py` keep their small local validation helpers. Their
domain contracts differ; no repeated-bug evidence justifies a schema DSL.
`evals/` remains synthetic deterministic calibration; `validation/golden/`
remains a real-public-paper candidate benchmark. Sharing mechanics does not
merge provenance categories.

The historical `scripts/validate_golden.py` itself is included in the B2 freeze.
Its bytes must remain unchanged, so its local mechanical code is an explicit
immutability exception. Current sibling scripts can stop importing it as a
library without rewriting the historical runner or its digest.

## Deferred decisions

**Architecture-level C1 remains deferred.** No static finding establishes that
a Skill, scientific object, lock, receipt or accounting abstraction should be
deleted, merged or renamed. C1a is only low-risk maintenance convergence.

Eleven human decisions remain pending, including the Diffusion Policy DDIM
10-versus-16 source discrepancy marked `GOLDEN_REVIEW_REQUIRED`.
This static audit does not establish populated-library acceptance. Any missing
real-data coverage must be reported separately and is not resolved by cleanup.
Repository visibility is an owner decision. The license was pending when this
audit was written; the owner has since selected [MIT](../LICENSE).

## C1a maintenance disposition

C1a applies the bounded maintenance findings above without changing the twelve
Skills, scientific records, source/retrieval behavior or audit evidence.

| Item | Disposition |
| --- | --- |
| Shared maintenance mechanics | `_validation_common.py` owns strict JSON, distinct byte/text digests, safe relative paths, original public identities, freeze checks and unchanged reviewed numeric mappings |
| Current script dependencies | Semantic and retrieval scripts import common directly; the frozen Golden runner is no longer a library for retrieval |
| Release source | `pyproject.toml` generates installed package metadata; runtime version, CLI and request identifier read that release |
| `project_version` / `language` | Removed from core defaults/examples; no runtime feature consumed them; old keys fail explicitly |
| `zotero.data_dir` | Removed: its sole use was validating its own config path, not Local API or environment reads; inspection retains required explicit `--zotero-data` and source/output containment |
| CLI `ingest` | Name and behavior retained; help states selected batch source archive, without Paper Note generation |
| Repository dependency duplication | Removed only installed-presence/version reporting; install, pip check and vulnerability audit remain separate CI gates |
| Document roles | README current entry; SPECIFICATION normative behavior; ARCHITECTURE current boundaries; other reports retain their dated evidence roles |

These are mechanical/configuration/documentation changes, not evidence for
architecture-level C1. No private sources are inspected and no human pending
decision is resolved by this maintenance stage.
