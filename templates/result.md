---
schema_version: 2
type: result-bundle
result_id: null
experiment_id: null
claim_id: null
claim_digest: null
design_digest: null
title: null
status: draft
verdict: NOT_TESTED
trial_ids: []
analysis_artifacts: []
missingness: []
evidence_ceiling:
  setting: []
  robot: []
  morphology: []
  task: []
  environment: []
  seeds: []
  replication: []
  ood: []
  transfer: []
synthetic: false
---

# Result Bundle

## Attempt coverage

Account for every relevant trial, including failures, aborts, exclusions and
retries. Explain missingness explicitly.

## Analysis and verdict

Link actual raw and analysis artifacts and compare observations with the frozen
claim and design. Preserve NOT_SUPPORTED and INCONCLUSIVE outcomes.

## Scope and deviations

State the evidence ceiling and any exploratory analysis separately from the
predeclared analysis. A draft contains no measured result by default.
