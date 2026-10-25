# Three-public-paper Golden candidates

Status: **Historical Phase B measurement; human Golden approval is pending.**
Phase B2 has since classified the nine semantic misses and measured Skill-level
retrieval at 6/6 versus raw 3/6. See the current
[semantic/retrieval report](SEMANTIC_RETRIEVAL_EVALUATION.md), including a new
`GOLDEN_REVIEW_REQUIRED` source discrepancy. The tables below preserve the
original run rather than overwrite its observed failures. Source evidence and
isolated integration have been checked, but human review and real Zotero binding
remain incomplete. This
candidate set was annotated on 2026-09-28 and integration-tested on 2026-09-29;
this report was finalized on 2026-10-03. It is not a benchmark score for a model.

## Sources and selection

| Paper | Role and selection reason | Fixed evidence source |
| --- | --- | --- |
| [Soft Actor-Critic](https://proceedings.mlr.press/v80/haarnoja18b.html), ICML 2018 | A: standard ML paper with a publisher citation, explicit algorithm and seeded evaluation protocol | PMLR main PDF, 10 pages; publisher record supplies no article DOI |
| [Diffusion Policy](https://www.roboticsproceedings.org/rss19/p026.html), RSS 2023 | B: 16-page source with formulations, figures, extensive tables and appendices; table conditions need careful separation | Seven-author RSS proceedings PDF; DOI `10.15607/RSS.2023.XIX.026` |
| [Sim-to-Real Transfer of Robotic Control with Dynamics Randomization](https://arxiv.org/abs/1710.06537v3) | C: 2017 preprint versus 2018 conference metadata; related manuscript/conference pagination differs and publisher access was blocked | Pinned arXiv v3, 8 pages; related conference DOI `10.1109/ICRA.2018.8460528` |

The RSS and current arXiv Diffusion Policy versions have different author lists.
Its conference record is not silently merged with the later journal manuscript.
An arXiv DOI is kept distinct from an article DOI; related identifiers do not
establish byte equivalence across versions. Sim-to-Real DOI verification used
arXiv metadata and the author's bibliography because the IEEE landing page
required an anti-bot challenge. Selected PDF hashes and precise one-based page
locators are in [annotations](../validation/golden/annotations/).

Original PDFs, extracted Fulltext, rendered page images, private paths and
temporary Vaults remain untracked. Public IDs, hashes, minimal paraphrased facts
and review metadata are committed. No paper PDF or lengthy excerpt is distributed.

## Independence and review records

Source annotators read primary metadata and original PDFs, extracted relevant
text and visually inspected evidence pages. They set claims, numbers, conditions,
scope cautions and two queries per paper without reading retrieval results or
captured answers. Paper C's annotator had worked previously on read-only guards
and synthetic safety tests; that exposure is disclosed in its review.

The capture author answered neutral questions directly from the PDFs. All three
answers were frozen in `5b9a97d` before that author inspected the annotations,
which were frozen in `1c75421`. The separately recorded [comparison](../validation/golden/comparison.json)
was frozen in `1faac7a`. Its manifest pins exact annotation/capture bytes, so a
changed statement cannot reuse an old review merely because its numbers match.
Queries and expected facts were not revised after measured failures.

These are **agent annotations and agent blind captures**, not human ground truth
or application-generated analytical output. Every paper has a `.review.md`
record with `human_reviewed: false`. The comparison reviewer authored paper A's
annotation, so A's comparison has disclosed author overlap; B/C were reviewed
across agents. Commit hashes prove preserved bytes, not a person's reading order.
Human acceptance of identity, meaning, scope, numerical conditions and locators
remains pending. The fuller limitations are in the [comparison review](../validation/golden/comparison.review.md).

## Workflow coverage and observed results

The [offline runner](../scripts/validate_golden.py) copies explicitly supplied,
hash-matched PDFs to a fresh OS temporary directory, creates an isolated Vault,
and removes that temporary workspace afterward. It uses an explicit temporary
configuration, bypassing personal configuration environment variables. The
input PDFs are read and fingerprinted before/after; no Zotero or other network
transport is used. Optional report export is exclusively created in a validated
repository/OS-temp workspace, separate from protected PDF inputs.

| Dimension | Observation | Status / practical limit |
| --- | --- | --- |
| Public paper identity | Title, publication year, article DOI where available, related arXiv identifier and pinned PDF version recorded for three papers | Source-reviewed candidate; human acceptance pending |
| Zotero identity / bibliographic intake | Canonical selection consumes three fixture parent/attachment records; nine explicit identifier-conflict probes rejected | Isolated coverage only; **0 real Zotero items bound** |
| Original PDF preservation | Three input and temporary-copy hashes unchanged | 3/3 pass in isolated run |
| Fulltext preservation | Three extracted body digests match; repeated archive reuses identical records; altered archive bodies detected | 3/3 pass; extraction does not certify every figure or formula |
| Canonical Note | Three schema-2 Notes authored from frozen blind captures; filenames use fixture parent keys | Pass in temporary Vault; these keys are explicitly not real Zotero keys |
| Note ↔ Fulltext | Six records bind matching parent/attachment/library identities; three broken-backlink probes detected | Pass in isolated run |
| Claim provenance | Nine claim sidecars resolve to source Notes and actual PDF pages; independent locators match 9/9 | Structural binding pass; free-text entailment requires review |
| Claim meaning / completeness | Agent comparison: 8 pass, 1 partial, 0 contradictions across nine claims | Partial: SAC objective capture omits the expected alpha-to-zero limiting case |
| Evidence scope | Captures retain source conditions; three overbroad-scope probes are not detected | Original deterministic coverage gap; semantic prose is evaluated separately in B2 |
| Numeric consistency | 26/26 expected numeric entries agree after explicit reviewed quantity/unit/condition mappings | Pass for mapped values; no automated condition understanding claimed |
| Retrieval | 3/6 predefined queries find the relevant paper: 3/3 term queries, 0/3 semantic paraphrases | **Fail** against the predefined relevance expectations |
| Claim Ledger | Three literature-only ledgers retain `NOT_TESTED`; source links and published claim IDs reconstruct the literature judgment | Pass for literature accounting; no local experiment was performed |
| Result accounting | Three attempts to promote literature-only ledgers to experimental `SUPPORTED` are rejected | Pass for that boundary; a valid local experimental Result Bundle is **not covered** |
| Vault validator | Nine records, zero errors and zero warnings; restoration after fault injection validates again | Structural baseline pass, with semantic misses below |
| Evaluation | Public-paper runner, independent comparison and existing numeric checker executed | Candidate measurement only; existing `eval-run` stays synthetic-only |

Fixture keys `GOLD0001`–`GOLD0003` and `PDFG0001`–`PDFG0003` exist only in the
isolated validation namespace; they do not identify items in a personal Zotero
library. Notes contain literature observations, not reproduced experiment
logs. No fabricated local Result Bundle or raw trial data was created to satisfy
an accounting schema.

The expected-number denominator contains 26 fact entries, including repeated
baseline facts across claims. It does not count independent measurements or
replications. The captures contain four further numbers, separately checked
against the source and excluded from that denominator. Source ambiguity such as
the Sim-to-Real displayed uncertainty's statistical definition is preserved.

## Predefined retrieval and error detection

| Query | Expected relevant claim | Relevant paper found |
| --- | --- | --- |
| `sac2018-q01`: temperature parameter | `sac2018-c01` | Yes, Fulltext fallback |
| `sac2018-q02`: performance checking / repeated-run aggregation paraphrase | `sac2018-c03` | No |
| `diffusion_policy2023_q1`: DDIM iteration/hardware terms | `diffusion_policy2023_c2` | Yes, Note |
| `diffusion_policy2023_q2`: responsive future movement planning paraphrase | `diffusion_policy2023_c1` | No |
| `sim2real2018-q1`: fixed action timestep | `sim2real2018-c2` | Yes, Note |
| `sim2real2018-q2`: episode-constant properties versus redrawn disturbances paraphrase | `sim2real2018-c3` | No |

Success is measured at **paper level**. The engine does not rank individual
claims. Its current all-token substring rule explains the missed paraphrases;
no query was simplified after this observation. No unrelated paper was returned
in these six queries. This small selected set is not a precision/recall estimate
for a broad literature corpus.

| Deliberately injected invalid cases | Detected / injected | Assessment |
| --- | --- | --- |
| Explicit parent/DOI conflict, arXiv version conflict, duplicate identifier | 9/9 | Detected by identity selection/conflict checks |
| Archived Fulltext drift | 3/3 | `FULLTEXT_DRIFT` |
| Broken reciprocal link | 3/3 | `RECIPROCAL_LINK` from the Vault validator |
| Impossible PDF page, fabricated exact quotation | 6/6 | `FABRICATED_PAGE` / `FABRICATED_QUOTE` at the target claim |
| Literature-only ledger promoted to `SUPPORTED` | 3/3 | Target `science.claim-ledger` diagnostic |
| Wrong numerical observation, overbroad scope, wrong table/experiment condition | 0/9 | Nine semantic false negatives |
| Total | **24/33** | **9 false negatives; 0 unscored cases** |

Baseline false-positive observations: **0 error/warning diagnostics across nine
valid records**. This is a narrow structural observation, not a measured false
positive rate on arbitrary notes. An unrelated diagnostic cannot count as
detecting a semantic injection: it is marked unscored. The observed semantic
misses returned no diagnostic. A valid page-bound observation establishes
location and provenance structure; the validator does not judge whether its
prose, number or scope is entailed by that page.

The committed [observed report](../validation/golden/reports/observed.json)
contains the actual hashes, query hits, target diagnostics and per-case outcomes.
It omits all original text and private machine paths.

## Failure classification and fixes

| Finding | Classification | Handling |
| --- | --- | --- |
| Missing SAC limiting-case detail | B: reading/capture completeness | Preserve partial label and frozen outputs; request human review |
| Semantic query misses | C: raw lexical recall limit; Skill layer not measured by this original runner | Original 0/3 preserved; B2 evaluates interpretation/expansion separately |
| Semantic observation/scope/condition misses | C: validator's structural boundary | Report nine false negatives; do not claim truth checking or weaken standards |
| PDF version, author, year and uncertainty differences | D: source ambiguity / manifestation differences | Pin source, disclose differences, retain uncertainty |
| Harness path/configuration, failure-log privacy and exit-accounting issues | A: validation implementation bugs | Regression first, then contained exclusive creation, explicit config, sanitized CLI failures and complete exit conditions |

One preliminary harness DOI scenario incorrectly treated filling an absent SAC
DOI as an identity conflict. The product correctly permitted that metadata merge.
The probe was corrected to an explicit parent selection with a conflicting
supplied DOI; the frozen source expectations and product standards were unchanged.
The initial reciprocal-link measurement was also replaced with a real disk
mutation and product validator call. Neither preliminary number is presented as
an accepted benchmark result.

## Reproduction and acceptance gates

```sh
# No PDF access; validates immutable inputs and reviewed numerical mappings only:
python scripts/validate_golden.py --check-inputs

# Supply the three explicitly acquired public PDFs with the recorded filenames:
python scripts/validate_golden.py --papers-dir PUBLIC_PDF_DIRECTORY --output-workspace .qa/phase2/local-review
```

The complete integration run intentionally exits **1** for measured gaps. A
successful `--check-inputs` or CI job means its input contract and regression
checks passed; it does not approve Phase B. Source PDFs are not downloaded in CI.
CLI failure logs export the exception type without private paths, and existing
reports are never overwritten.

The [architecture gate record](ARCHITECTURE_AUDIT.md) separates C0 read-only
audit from C1 changes. Pending human approval or missing populated-library
evidence may permit only C0 after B2 evidence and current regressions/CI pass.
If an installation has no suitable real records, report that coverage as
`BLOCKED_EXTERNAL`; do not manufacture records to claim real-data acceptance.
The B2 measurement performs no architecture audit or deletion. Subsequent C0
static findings are recorded in that audit file; C1a maintenance does not revise
these Golden outcomes or complete pending human decisions.
