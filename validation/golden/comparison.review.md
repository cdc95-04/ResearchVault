# Frozen capture comparison review

Status: `agent_comparison_pending_human`. **No human has reviewed or approved this comparison.**

The comparison covers the three frozen captures at commit `5b9a97d075726d2ce5cb50ea62971edf8689ced9`. Their working-file bytes were checked against that commit. Annotation and source-PDF hashes are recorded in `comparison.json`; no annotation or capture was modified to improve agreement.

## Results

- Statements: **8 pass, 1 partial, 0 fail** across 9 claim records.
- Evidence locators: **9/9 matched** the same source passages or table evidence.
- Expected numerical fact entries: **26/26 matched**, after explicit semantic mapping to capture number names and review of units and conditions.
- Capture number entries: **30 total**. The **4 extras** were checked directly against the source PDFs and are reported separately; they do not increase the expected-fact numerator or denominator.

The partial record is `sac2018-c01`: the capture correctly explains the entropy objective and temperature weighting, but omits the expected alpha-to-zero limiting case. This is a missing expected detail, not a fabricated capture claim. Because that detail is in the annotation statement rather than its `numeric_facts` list, **26/26 numerical agreement does not mean complete claim coverage**.

Each numeric mapping is keyed by `golden_index` and the capture's explicit `name`. The written rationale identifies the quantity and experimental condition before comparing values. Abbreviated number fields were interpreted together with their full capture statement and scope. Numerical coincidence alone was not accepted.

## Independence disclosure

This reviewer originally authored the SAC annotation. Paper A is therefore a disclosed self-review of that annotation against a separately produced, frozen blind capture, not a second independent annotation author. Papers B and C are cross-agent annotation reviews. The parent reports that its captures were written from the blind questions and original PDFs before reading the annotations; the commit and byte checks establish the freeze, but cannot independently prove the earlier reading process.

The reviewer read the original evidence PDFs and frozen JSON, with visual checks of the SAC formula/experiment pages, Diffusion Policy tables, and Sim-to-Real tables. A separate source-only helper checked evaluation aggregation and uncertainty/trial conditions without reading capture JSON. No application source, tests, existing program-generated results, or retrieval outputs were consulted. These are agent comparisons of agent captures, not a measurement of application extraction quality.

## Source limits preserved

- **Sim-to-Real uncertainty:** The checked page 7 discussion and Table II/III captions do not define the displayed plus/minus entries as SD, SEM, or confidence intervals. Their values and row conditions match; their statistical meaning remains unspecified. No interpretation was inferred from resemblance to a statistical formula.
- **Sim-to-Real repeated baseline:** Table III's all-parameters entry repeats the Table II LSTM real-robot result. Multiple matching fact entries do not establish additional trials or an independent replication.
- **Diffusion Policy aggregation:** The table captions and Section V.B support the checkpoint, seed, and environment-initialization counts. They do not establish whether initialization sets are independently resampled or reused across seeds or checkpoints. The extra initialization count is accepted only within this limited protocol meaning.
- **Diffusion Policy source processing:** `pypdf` emitted a numeric-format warning. Relevant table cells, headers, and captions were also visually inspected. No malformed plot text was used to establish the numerical matches.
- **Versions and page numbering:** Comparisons use the hashed PMLR SAC PDF, RSS conference Diffusion Policy PDF, and pinned arXiv v3 Sim-to-Real PDF. Locators refer to one-based PDF pages. Related arXiv records or conference manifestations are not asserted byte-identical.
- **Scope of totals:** The denominator counts expected `numeric_facts` entries, including entries repeated across different claims. It is not a count of unique measurements, independent trials, or human-reviewed facts.

The evidence is available in the [SAC publisher PDF](https://proceedings.mlr.press/v80/haarnoja18b/haarnoja18b.pdf), [Diffusion Policy RSS PDF](https://www.roboticsproceedings.org/rss19/p026.pdf), and [Sim-to-Real arXiv v3 PDF](https://arxiv.org/pdf/1710.06537v3). Precise claim-level locators and extra-number source checks are in the comparison JSON.

Retrieval false positives, false negatives, precision, and recall are outside this review and have not been estimated. Human review remains pending for all statement, scope, locator, and numerical-condition judgments.
