# Phase B2: responsibility and retrieval evaluation

Historical B2 evidence snapshot, completed at
`2ec9afeb1f591c1bab41ad173f04c85cda4df5ab`. Later C0/C1a maintenance does not
rewrite these measurements or approvals. Current entry status is in
[README](../README.md); static findings are in [C0 audit](ARCHITECTURE_AUDIT.md).

Baseline: `1f53e4ea5b805f0fedd52cc075df0997470b9f58`. This stage preserves the
original candidate Golden and stops before architecture work. The original
Phase B report remains a historical measurement; this report distinguishes
structural checks, semantic judgments and human approval.

## Frozen inputs

[freeze.json](../validation/golden/b2/freeze.json) pins thirteen original text
files, including the deliberate-invalid generator, all three public PDF
identities/hashes/versions, nine expected claims, original blind captures,
26 numerical expectations, six queries and 33 deliberate-invalid cases.
Text SHA-256 normalizes CRLF to LF for checkout portability and preserves every
other byte; PDF SHA-256 uses original bytes. The invalid inventory also has a
stable canonical JSON digest. No original annotation, capture, comparison,
query, numeric expectation or observed report is revised in B2.

## Deterministic and semantic ownership

All nine old semantic misses are reproduced from the original frozen mutators
and last captured claim for each paper. Their free-text observation/scope fields
do not expose an exact calculable scientific constraint. Primary ownership:

| Owner | Cases |
| --- | ---: |
| STRUCTURAL_VALIDATOR | 0 |
| SEMANTIC_EVAL | 9 |
| HUMAN_REVIEW | 0 |

The last row means no case is blocked on an ambiguous semantic adjudication.
It does **not** mean human approval is complete. Nine semantic cases and the SAC
revision still require human confirmation, alongside any separately flagged
Golden source ambiguity.

Deterministic validation retains schema, identity, DOI/key consistency,
Note/Fulltext links, pointer existence, page bounds, supplied exact quotations,
explicit numerical mappings, structured unit/scope fields, provenance, digests,
locks, denominators, trials and required experimental metadata. It cannot prove
entailment, causality, mechanisms, concept equivalence, unrestricted prose scope,
experimental interpretation or absence of omitted qualifiers. There are no new
scientific keyword heuristics and no runtime validator or numerical checker
changes. Evaluation-fixture reconstruction only checks preservation of the
original injected bytes; it does not detect semantic error.

[Cases](../validation/golden/b2/semantic_cases.json),
[rubric](../validation/golden/b2/semantic_rubric.json),
[blind captures](../validation/golden/b2/semantic_captures.json) and
[mapped results](../validation/golden/b2/semantic_results.json) stay in a flat
maintenance directory. The ten dimensions return PASS, FAIL, UNCERTAIN or
HUMAN_REVIEW_REQUIRED, never a numerical score. The contract checker validates
structure and source integrity, not the scientific verdict.

One independent-context Astra Ultra reviewer received frozen sources,
candidates and rubric, without expected verdicts, previous adjudication or
generation reasoning. It inspected the hashed PDFs, relevant pages and context;
all nine injected candidates received **FAIL**, with claim, source evidence,
missing qualifier, scope/condition mismatches and anchors. The root agent
mapped blind IDs without changing judgments. This is `agent_review`; all human
statuses remain `pending`. Reviewer declarations document the process rather
than cryptographically proving reading order.

## SAC partial capture

The publisher PDF p.3, §3.2 Eq.1 and its following paragraph preserve the α→0
limiting condition. The stored agent capture omits it. The demonstrated cause is
candidate generation/capture coverage omission, not a proven application bug.
The original extraction window, generation trace and pre-serialization draft
are unavailable, so those internal causes cannot be distinguished conclusively.
Existing source-grounded Skill requirements are adequate; no SAC keyword rule
or special instruction was added.

[Separate revision](../validation/golden/b2/sac_revision.json) appends only the
source-supported limiting condition. An independent source-only
[agent review](../validation/golden/b2/sac_revision_review.json) returns PASS,
while noting that “optimal-policy stochasticity” is the precise source wording.
The original 8 PASS / 1 partial comparison remains frozen. The new revision is
agent-reviewed, not a replacement human ground truth; numbers are unchanged.

## Two retrieval layers

The old six-query runner called `fulltext.retrieve` directly. That primitive is
all-token case-insensitive substring recall in traversal order. The existing
literature-retrieval Skill supplies interpretation, bounded expansion, local
calls, namespaced deduplication and inspected-source verification. SPECIFICATION,
ARCHITECTURE and the existing Skill now state this boundary explicitly.

An answer-blind planner saw only queries and existing contracts, then froze
the original query plus three expansions per request in commit `88a0166`, before
seeing any corpus or results. Each plan preserves relation type and rationale;
all four calls share a fixed budget. The unchanged raw retriever gates Fulltext
when Note recall is empty. A fresh temporary corpus contains three original
frozen Notes, three hashed Fulltexts and original claim bindings; no artificial
Knowledge or private library data is inserted. Read-only calls preserve it.

The expanded relevance contract keeps original queries and targets, records
acceptable alternatives, distractors and minimum evidence before execution.
The unspecified performance-protocol question permits another fully supported
protocol. A filename hit alone cannot pass. An answer-blind verification step
inspects returned candidates and PDF pages, rejecting unrelated matches.

| Original query | Raw | Skill | Inspected answer |
| --- | --- | --- | --- |
| SAC temperature parameter | PASS | PASS | §3.2 objective and optimal-policy stochasticity; α→0 limit |
| SAC performance cadence / repeated runs | FAIL | PASS | SAC p.7 protocol; Diffusion Policy p.7 is also a valid alternative protocol |
| Diffusion Policy DDIM / iterations / GPU latency | PASS | PASS | Main-text p.4 configuration, with appendix discrepancy disclosed |
| Diffusion Policy responsive future sequence | FAIL | PASS | p.3 receding horizon, observation/prediction/action horizons |
| Sim-to-Real fixed action timestep | PASS | PASS | Constant-timing comparison distinguished from randomized timing |
| Sim-to-Real episode-constant / redrawn properties | FAIL | PASS | p.4 sampling procedure and runtime disturbances |

Raw = **3/6**, Skill = **6/6**. Across expanded retrieval, thirteen returned
paper/query candidates were reviewed: seven PASS, five FAIL and one UNCERTAIN.
The uncertainty concerns a non-required alternative for the timing question;
it is not counted as accepted evidence. Broad expansions are not assumed
precise: rejected/uncertain sources remain in the capture.

The scoped retrieval acceptance is **PASS**. This small three-paper benchmark
supports Skill responsibility for semantic interpretation/expansion, not a
universal recall/precision claim. It provides no evidence that a new semantic
backend is necessary. No embeddings, vector database or runtime dependency was
introduced; backend design comparison was not triggered by the observed result.
See [plans](../validation/golden/b2/retrieval_plans.json),
[relevance cases](../validation/golden/b2/retrieval_cases.json),
[raw/call/rank/matched-term records](../validation/golden/b2/retrieval_observed.json),
[source judgments](../validation/golden/b2/retrieval_captures.json) and
[accounted results](../validation/golden/b2/retrieval_results.json).

## New source ambiguity, original Gold preserved

Diffusion Policy p.4 §III.D states real-world DDIM 100 training denoising
iterations, 10 inference iterations, 0.1 s on Nvidia 3080. Appendix p.14 D and
p.15 Tables VI–VII give real-world inference 16, with table training 100, for
both CNN and Transformer. The identified PDF does not map 10 versus 16 to
distinct setups. The 0.1 s latency cannot be transferred to the 16-step account.
An independent source-only Astra review returns HUMAN_REVIEW_REQUIRED.

[GOLDEN_REVIEW_REQUIRED](../validation/golden/b2/golden_review_required.json)
preserves the entire original c2 annotation and both source accounts via the
[source review](../validation/golden/b2/golden_source_review.json). The original
26 numeric entries and expected answer remain unchanged. The scoped retrieval
answer reports both accounts and their unresolved discrepancy; a whole-PDF
unqualified unified setting is not accepted. This is a new pending source
review, not permission to silently repair Gold.

The human packet has **10 planned decisions + 1 new source-discrepancy decision**;
all remain pending. No agent label has been promoted to human review.

## Regression and gates

The original numerical mappings still agree **26/26**; this measures equality
under reviewed mappings, not absence of source ambiguity. The original
deterministic invalid measurement remains **24/33**. Semantic adjudication is
reported separately as nine failed injected candidates, never relabeled as
33/33 automatic-validator detections.

The benchmark uses an isolated corpus without writing to a real Zotero library
or Obsidian Vault. Preserve inputs and source PDF hashes; containment, privacy,
no-secret/no-PDF and read-only regressions remain required. The benchmark does
not supply populated-library acceptance. If suitable real records are absent,
report that separate coverage as `NON_EMPTY_REAL_LIBRARY_VALIDATION = BLOCKED_EXTERNAL`.

Run the current regression suite, repository/resource audit, dependency checks
and hosted CI before using the C0 gate. Record actual failures and platform
capability skips in private run evidence; do not infer native link or long-path
support from another environment. Keep the twelve-Skill contract and prevent
PDFs, private paths and secrets from entering tracked files. The six-record
synthetic Vault retains its six declared missing-source warnings. Hosted CI
supplies tested-platform evidence separately from live library acceptance.

Phase C0 may begin as a **read-only static audit** only after agent adjudication,
SAC cause localization, the Skill benchmark, structural regressions, the full
current suite and CI pass. Human Golden approval and populated-user-data checks
may remain pending. Phase C1 deletion/merge/rename/removal is deferred until
sufficient real-use evidence; this stage performs neither C0 nor C1.

## Reproduce

```sh
python scripts/semantic_contract.py --sac-revision
python scripts/benchmark_retrieval.py --check-recorded
# Add --papers-dir PUBLIC_PDF_DIRECTORY to check original PDF bytes/page counts.
python scripts/benchmark_retrieval.py --papers-dir PUBLIC_PDF_DIRECTORY --output-workspace .qa/b2/new-run
python -m unittest discover -s tests -v
```

The retrieval runner measures candidates and exports an ignored source packet;
it never manufactures an agent judgment. Re-execution requires a new exclusive
output directory. Committed captures/results preserve the observed agent
judgments; CI checks their contract and regressions without downloading PDFs or
pretending to rerun a model. The small [human packet](HUMAN_REVIEW_PACKET.md)
contains the cases requiring owner decisions.
