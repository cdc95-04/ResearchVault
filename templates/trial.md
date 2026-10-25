---
schema_version: 2
type: experiment-trial
trial_id: null
experiment_id: null
design_digest: null
condition: null
seed: null
robot: null
environment: null
git_commit: null
config: {}
raw_artifacts: []
status: draft
abort_reason: null
exclusion_reason: null
missingness_reason: null
included_in_denominator: null
retry_of: null
synthetic: false
---

# Trial record

## Attempt and observations

Record only the attempt that occurred and its real artifacts. Keep failed,
aborted and excluded attempts; a retry receives a new trial_id.

## Accounting decision

Resolve inclusion using the frozen policy and state the reason for a deviation
or missing raw evidence. Do not infer a null outcome from missing data.
