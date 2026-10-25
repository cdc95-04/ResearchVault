# Evaluation failure categories

| Criterion / category | Severity | Meaning and response |
| --- | --- | --- |
| fabrication | critical | A mapped assertion or locator-bound quote lacks source support; preserve the capture and inspect it. |
| source_identity | critical | The capture points at a different source identity. |
| source_digest | critical | Source binding is absent, stale or unverifiable because the capture is missing. |
| evidence_ceiling | critical | The claimed scope exceeds the source's explicitly allowed scope. |
| evidence_label | critical | The evidence state differs from the source expectation. |
| behavior | major | A workflow decision differs from the case expectation, such as denominator loss or inconclusive promotion. |
| numerical_consistency | major | Explicit occurrences differ, have incompatible units, or lack required locations. |
| missing capture | per criterion | The case is unevaluated; it cannot count as a pass. |
| golden disagreement | review gate | An observed label differs from the authored golden; request human review without rewriting either side. |
| incompatible runs | comparison gate | Measuring rules or common sources differ; rerun both versions against the same rules. |
| malformed input | input error | Duplicate IDs, invalid paths, nonfinite values or invalid schemas stop evaluation. |

These categories describe deterministic checks over structured synthetic data.
They are not an exhaustive taxonomy of research mistakes or a scientific fraud
detector. A passing case can still contain unassessed free-form prose.
