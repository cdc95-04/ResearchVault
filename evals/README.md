# Captured-output calibration

These eight cases are freshly authored **agent-curated synthetic** examples.
They are not papers, exports from a personal Vault, model-generated benchmark
runs, or human-reviewed real evidence. No network or model call is involved.
The real-paper benchmark has not been started in phase one.

The evaluator checks structured factual assertions, exact quotations at explicit
locators, source identity, allowed scope, evidence labels, expected workflow
decisions and explicitly mapped numeric values. It cannot decide whether free
prose is scientifically correct, whether a paper was read, or whether an
experiment actually happened. The hand-authored sources are calibration inputs,
not independent scientific ground truth.

| Case | Deliberate behavior | Expected outcome |
| --- | --- | --- |
| bounded_note | Preserve the inconclusive result and its setting | pass |
| invented_quote | Insert text absent from the named source segment | critical failure |
| publication_swap | Identify a different source | critical failure |
| scope_escalation | Add hardware transfer to simulation-only scope | critical failure |
| all_attempts | Retain completed, failed and aborted attempts | pass |
| inconclusive_promotion | Rename inconclusive as supported | failure |
| bounded_review | Keep an unexecuted challenge query as a limitation | pass |
| number_drift | Change one mapped caption value | failure |

Run from the repository root:

```sh
python -m researchvault eval-run evals/synthetic-suite.json evals/fixtures/calibration-captures.json
python -m unittest discover -s tests -p test_evaluation.py
```

The first command intentionally exits **1**: it detects five defective captures
and three valid captures. `golden_agreement: true` means the checker agrees with
all authored calibration labels; it does not turn the defective captures into
passing research outputs. Unit tests verify evaluator mechanics, including
calibration agreement. Their count is not a real research benchmark score.

`--output evals/results/local-run.json` optionally writes a report, exclusively
creating a new file. Existing output and source files are never overwritten.
Reports under results are local artifacts and ignored by Git. Compare two
saved reports with:

```sh
python -m researchvault eval-compare evals/results/before.json evals/results/after.json
```

Each criterion exposes `expected`, `observed`, `status`, `severity` and `evidence`.
Reports bind source bytes, capture content, rubric bytes/version, suite bytes and
golden bytes by SHA-256. The hashes detect differences; they do not authenticate
an author or prove correctness. Missing captures remain visible as `missing`,
including critical source failures. A golden disagreement sets
`human_review_required` and requests review without changing the golden, source
or capture. Human review in this context is a request, not a completed review.

Comparison lists regressions, improvements, unchanged criteria, new failures,
added cases and removed cases. A changed rubric, suite version, provenance, or
shared case's source/definition/golden requires re-evaluation under matching
rules. Adding cases is allowed when the common cases and measuring rules are
unchanged. Removed cases prevent a successful comparison. Capture hashes may
change between runs; otherwise output improvements could never be compared.
Missing-to-failing remains an unresolved failure rather than an improvement.

## Input contracts

`synthetic-suite.json` names a versioned rubric, a golden file and local source
fixtures. Paths stay inside the suite directory, including through symlinks.
The rubric uses only deterministic `equals`, `subset`, `grounded_claims` and
`mapped_numbers` operators. Critical fabrication, source identity and evidence
ceiling checks are mandatory. Fixture `facts` provide exact key/value assertions;
fixture `segments` map explicit locators to text. This is deliberately a small
format rather than a general evaluation framework.

Capture manifests carry `run_id`, `producer_version`, `provenance` and a
`captures` mapping from case ID to `{source_digest, output}`. Source digests use
the source file's exact UTF-8 bytes. Each output contains `source_id`, explicit
`claims` and `quotes` lists, `evidence_scope`, `evidence_status`, `assessment` and
`number_claims`. Empty claims/quotes lists explicitly mean no such assertion;
missing lists fail the fabrication check. Unknown case IDs and duplicate JSON
keys are errors rather than silently ignored input.

Every suite, source, golden and capture manifest must carry these exact flags:

```json
{
  "kind": "agent-curated synthetic",
  "synthetic": true,
  "human_reviewed": false,
  "real_papers": false
}
```

`human-reviewed real` is a separate future category. Changing those flags does
not create that benchmark; phase-one execution rejects real inputs.

## Explicit numeric mapping

`numbers` accepts a list of claim objects, `{ "claims": [...] }`, one claim
object, or an object mapping claim IDs to claim objects. It compares every
supplied occurrence, including locations in addition to the required list.
Names such as abstract, body, table, caption and ledger are user-supplied mapping
labels; there is no guessed association or text extraction.

```json
{
  "claims": [{
    "claim_id": "toy_success_rate",
    "unit": "fraction",
    "tolerance": 0,
    "required_locations": ["abstract", "body", "table", "caption", "ledger"],
    "occurrences": [
      {"location": "abstract", "value": 0.5, "unit": "fraction"},
      {"location": "body", "value": 0.5, "unit": "fraction"},
      {"location": "table", "value": 0.5, "unit": "fraction"},
      {"location": "caption", "value": 0.5, "unit": "fraction"},
      {"location": "ledger", "value": 0.5, "unit": "fraction"}
    ]
  }]
}
```

Save this as a JSON file and run `python -m researchvault numbers path/to/file.json`.
Tolerance is absolute in the declared unit, using the span of all occurrences.
Units must match exactly; percent/fraction conversion is never implicit. Missing
locations, duplicate locations, booleans and nonnumeric values fail. At least two
distinct required locations are necessary. Empty claim collections return
`not_applicable`, not evidence of a numeric consistency review. Disagreement
reports every supplied value without choosing which value is scientifically
correct. Numeric agreement alone cannot establish source accuracy.
