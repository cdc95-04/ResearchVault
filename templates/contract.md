---
schema_version: 2
type: experiment-contract
experiment_id: null
card_id: null
claim_id: null
claim_digest: null
title: null
status: draft
conditions: []
baselines: []
metrics: []
denominator:
  unit: null
  include_statuses: [completed, failed, aborted]
exclusions: []
abort_policy:
  allowed_reasons: []
  include_in_denominator: true
seeds: []
analysis_plan: null
design_lock_status: draft
design_digest: null
design_receipt: null
synthetic: false
---

# Experiment Contract

## Question resolved by this design

Link the frozen claim and explain the contrast each condition supplies.

## Measurement and accounting

Define metric calculation, denominator unit, exclusions, abort reasons and
missing-data handling before observing results.

## Execution and analysis specification

Record required configuration, randomization, analysis and evidence artifacts.

## Design decision and deviations

Review the snapshot before applying a Design Lock. Preserve original receipts
and record a revision instead of rewriting the meaning of earlier trials.
