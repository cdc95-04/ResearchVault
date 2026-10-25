# Implementation provenance

This repository begins a new Git history. No prototype directory, source file,
test file, README, Skill prose, template or .git directory is imported. Authors
have previously worked on the prototype, so this is an independent reimplementation
from requirements, not a claim of a legally isolated clean-room process.

| Classification | Source / treatment |
| --- | --- |
| User requirement | Independent ResearchVault requirements, normalized into SPECIFICATION.md |
| Independent implementation | New researchvault package, tests, templates, Skills and documentation authored against those behaviors |
| Design reference | Earlier cdc95-04 prototype branch, including its published workflow behavior; no runtime dependency or copied files |
| Design reference | Robotics-Research-Skill, auto-paper-collector, yananlong/codex-skills, codex-research-assistant and original Zotero workflow; ideas only |
| Licensed code dependency | PyYAML; optional pypdf and fonttools; build/test tools installed as packages, never vendored |
| Official API specification | Zotero Local/Web API, Crossref REST, Unpaywall API and arXiv API; implementation reads the official contract directly |

The source inventory and license observations are in THIRD_PARTY_NOTICES.md.
Their license labels apply to examined reference snapshots, not to this entire
project. A package dependency's own license remains with its distribution,
including the notices for external components supplied with fonttools.

## Phase-one source review, 2026-09-27

The independently authored working tree was compared after implementation with
the prototype at `a699e64fc7a364281d6f5909981320cca9fb0936` and original upstream at
`fb95dda1afb4b824aa3922b44bdbd4161e9e8ab9`. The final stable scan covered 104 new
files, 117 prototype files and 31 upstream files; no file changed during that scan.
The comparison ran locally as an ignored audit artifact, not a runtime dependency.

- No byte-identical or whitespace/line-ending-identical files were found.
- Contiguous normalized-line, word and Python-token comparisons flagged import
  lists, the required canonical folder-name map, six standard unittest temporary
  directory setup fragments and one short DNS/global-IP check using Python's
  standard library. The latter is 39 tokens / 124 characters, three lines. These
  were inspected as common field names and short programming idioms, not
  substantial source or narrative-prose reuse.
- No narrative-prose run of at least 24 words, or Python run of at least 70 tokens
  after identifier/literal normalization, was found. Exact Python-token review
  used a 35-token threshold; normalized-line review used three nonblank lines and
  at least 100 nonspace characters.
- New history has one root, `562ce8515c82a22074956d65482a6e94b1328038`, and no
  common commits with the old repository. No submodule, vendored reference source,
  `rvault` import or prototype runtime path is present.
- Runtime dependencies are installed from their own distributions. The authored
  package, tests, twelve Skills, twenty-two templates and synthetic eval inputs
  were written against the new specification. Parallel implementers did not read
  old implementation/test/prose files while authoring; later comparison was
  read-only. Official API documentation supplied wire protocol requirements.
- The tracked-file scan checked Skill inventory, resource links, private artifact
  extensions, common credential patterns, personal absolute paths and synthetic
  labels. No flagged secret/private artifact remained. This is a heuristic scan,
  not comprehensive secret detection.

No substantial copied implementation or prose was identified in the reviewed
snapshots. Exact contiguous matching can miss paraphrases and reordered logic,
and these two comparisons do not cover every external repository revision.
The audit cannot establish historical authorship or legal clearance. At the time
of this review, the project remained private and its license was pending owner
selection. The owner has since selected the [MIT license](LICENSE); this does not
change the scope of the source review or authorize making the repository public.

No live personal library, paper PDF or real Vault content has been used in phase
one. All six example records and eight eval cases are explicitly synthetic.
Unit-test success and evaluator calibration do not certify real-environment
interoperability or scientific truth. The phase-one delivery report records the
actual test and CI results at its final commit.

## Phase-two evidence sources, 2026-09-28

Private installation inspection is separate from the public-paper benchmark.
Any database copies, private inventory, registry paths and fingerprints belong
in ignored operational storage, not the repository. The benchmark does not
establish the content or interoperability of a personal library or Vault.

Three public papers now supply minimal derived facts for candidate validation:
[Soft Actor-Critic](https://proceedings.mlr.press/v80/haarnoja18b.html),
[Diffusion Policy](https://www.roboticsproceedings.org/rss19/p026.html), and
[Sim-to-Real Transfer](https://arxiv.org/abs/1710.06537v3).
Tracked material contains public identifiers, source hashes, paraphrased
annotations, blind captures, and review metadata. Full PDFs, extracted Fulltext,
page images and temporary Vaults are not redistributed. This change in evidence
provenance does not establish any new license for the repository.

Source annotators did not consult paper-processing outputs. The capture author
answered neutral questions directly from PDFs and froze all three captures in
`5b9a97d` before reading the annotations, frozen in `1c75421`. Paper C's annotator
had previously worked on read-only guards and synthetic safety regressions; that
limited prior implementation exposure is explicitly disclosed in its review.
These are independent agent annotations, not completed human ground truth.
The subsequent comparison is separately labeled agent review. The repository
does not claim a human-reviewed benchmark or legal clearance from these checks.

## Phase B2 responsibility review, 2026-10-04

The original Golden inputs and generator remain frozen at the phase-two
baseline; text digests normalize line endings only. One independent-context
`gpt-6-astra` / `ultra` reviewer received source/candidate/rubric without expected
errors, earlier verdicts or generation reasoning. Root only maps its nine blind
IDs. SAC's separate proposed revision was source-reviewed without its generation
reasoning or the original Gold. These are agent judgments; human status remains
pending. Context declarations are recorded, not asserted as cryptographic proof.

An independent retrieval planner froze six original queries and bounded
expansions before inspecting the corpus or expected answers. After execution,
that agent verified returned sources against the original queries without Gold.
The expanded relevance contract was separately frozen before execution. Raw
lexical and Skill evidence acceptance are distinct measurements. No model
backend, vector database or new user-facing Skill was added.

Source inspection also exposed conflicting real-world DDIM inference counts in
the same RSS PDF: main text 10 versus appendix 16. A source-only Astra review
preserves both and requests Golden review; original annotation values are not
changed. All new tracked source material remains minimal public facts, paraphrases
and review metadata, with PDFs/Fulltext/images ignored as before.
