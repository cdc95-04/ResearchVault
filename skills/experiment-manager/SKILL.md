---
name: experiment-manager
description: Maintain experiment Contracts, Design Locks, complete Trial accounting and evidence-bounded Result Bundles for an explicit research claim.
---

# Experiment manager

Read [science](../../references/science.md) and only the needed
[contract](../../templates/contract.md), [trial](../../templates/trial.md) or
[result](../../templates/result.md). Use a real Claim Lock reference; a draft
claim cannot silently become a frozen premise.

Define conditions, baselines, metrics, denominators, exclusions, abort policy,
seeds and analysis before freezing the design. Preview the snapshot metadata.
Changes require an existing predecessor and reason, preserving all historical
result references; post-result revisions remain exploratory.

Register every attempt with experiment/design identity, condition, seed,
robot/environment, exact code commit, config, raw artifacts, status and explicit
denominator decision. Keep failed, aborted, excluded and retried attempts.
Connect retries to the preceding attempt. Missing raw data requires a reason and
does not permit deletion from accounting.

Compile a Result Bundle over all relevant attempts. Check abort/exclusion rules,
denominator, missingness, raw evidence and analysis artifacts against the design.
Use SUPPORTED, NOT_SUPPORTED, INCONCLUSIVE or NOT_TESTED as justified; negative
and inconclusive results are valid outputs. Do not infer a verdict from a record
being structurally valid.

Report deviations and evidence ceilings with the result. This Skill records
scientific work; it does not run robots, invent artifacts or treat a lock as an
execution permit. Hand writing claims to writing-support.
