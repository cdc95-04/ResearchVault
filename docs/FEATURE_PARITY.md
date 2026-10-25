# Historical Phase-One Parity Snapshot

This is the independent implementation's phase-one parity evidence. Its table
records that stage's scope and synthetic checks. Later B/B2/C work does not
rewrite these rows as though it had been part of the original phase-one result.
Current entry status is in [README](../README.md); later measurements have their
own environment, Golden and B2 evidence reports.

This table compares the required prototype behavior with the new implementation,
not old file bytes or CLI compatibility. “Implemented” means the listed synthetic
checks exist; it does not claim live integration, scientific correctness or a
human-reviewed real-paper benchmark.

| Prototype behavior | New ResearchVault behavior | Status | Test | Notes |
| --- | --- | --- | --- | --- |
| Configurable Vault layout | Explicit external roots, configured roles/categories, containment | Implemented | `test_core.ExplicitStorage` | No default personal Vault; synthetic exceptions explicit |
| Stable source identity | Namespaced parent/attachment, DOI/arXiv version, collision stop | Implemented | `test_core.NamespacedIdentity` | Titles remain lookup hints |
| Source / Note / Knowledge separation | Reciprocal references, excerpts, PDF pages, counts and provenance | Implemented | `test_fulltext.SourceWorkflow` | Partial evidence warns; completion/verification needs artifacts |
| Original Fulltext storage | Text/cache/structured-input preservation; optional pypdf extraction | Implemented | `test_archive_preserves_original_and_does_not_create_analysis` | Structured parser is external input; no automatic scientific interpretation |
| Reusable initialization | Missing folders/templates only | Implemented | `test_init_is_preview_then_create_only` | One canonical repository templates/ directory |
| Local literature retrieval | Note/Knowledge first, Fulltext on explicit request or empty Note recall | Implemented | `test_local_recall_has_real_counts_and_explicit_layers` | Parent counts deduplicated; no global coverage claim |
| Selected batch orchestration | Serial archive plan/apply with per-item blocked outcomes | Implemented | `test_ingest_is_selected_serial_and_keeps_blocked_item` | Does not manufacture analytical Notes |
| Conservative migration and edits | Read-only inventory and proposed diffs | Implemented | `test_diff_and_migration_never_modify_records` | Personal schema/receipt conversion remains manual |
| Existing Zotero access | Paginated Local API inventory and bounded parent/PDF resolution | Implemented | `test_zotero` read-only cases | Live interoperability deferred; no SQLite mutation |
| Safe create-only intake | Explicit writes, conditional upload, durable intent and readback | Implemented | `test_zotero` mutation/uncertain-outcome cases | No real writes in phase one; preserve annotations/attachments |
| External discovery | Canonical Crossref metadata and DOI/version dedup | Implemented | `test_intake` discovery cases | Crossref is the initial adapter; no automatic arXiv–DOI equivalence |
| Lawful acquisition | Selected Unpaywall DOI routes, serial limits, resume hashes, PDF states | Implemented | `test_intake` acquisition cases | Unclear PDF/version stays probable/ambiguous; no auto-ingest |
| Scientific object progression | Distinct Question, Gap, Hypothesis, Idea, Card, Contract, Trial, Result, Ledger | Implemented | `test_science` plus canonical templates | Skills guide human scientific work; no robot execution engine |
| Claim / Design Lock | Canonical SHA-256 receipts, predecessor/reason and exploratory revisions | Implemented | `test_science`, `test_provenance` | Local integrity record, not trusted timestamp |
| Complete attempt accounting | Fail/abort/exclude/retry retained; policy and missingness checked | Implemented | `test_failed_aborted_excluded_and_retry_all_remain_accounted` | Result accounts for all registered attempts of the bound design |
| Evidence ceiling and verdicts | Separate experimental judgments, ledger result bindings and scope ceiling | Implemented | `test_ledger_cannot_promote_inconclusive_or_expand_robot_scope` | Negative/inconclusive are valid outcomes |
| Systematic review | Protocol, families, seeds, chaining, challenge searches, screening, coverage | Implemented | `test_review` | No paper quota or invented absence proof |
| Corpus Freeze / Gap gate | Versioned corpus snapshots and source-bound critical evidence | Implemented | `test_high_gap_requires_actual_critical_source_evidence` | Coverage has limits; high confidence is not machine-certified truth |
| Optional provenance snapshots | Source/input hashes, finite JSON, immutable history | Implemented | `test_provenance` | Ordinary Concepts need no digest sidecars |
| Writing number checks / research eval | Explicit mapped values and captured-output criteria with regression comparison | Implemented | `test_evaluation` | Agent-curated synthetic calibration; not a real benchmark |
| Twelve progressive Skills | Exactly the canonical twelve entries with scoped resources | Implemented | `scripts/audit_repository.py`, Skill frontmatter check | Single task does not load all contracts |
| Release checks | Three OS × two Python versions, dependency/secret/path/link scans | Implemented | `.github/workflows/ci.yml` | Heuristic scans have documented limits |
| Real Zotero / Obsidian and three real papers | Intentionally stopped at phase-one boundary | Deferred by instruction | None claimed | Read-only stage requires the phase-one report first |

The initial distribution is an editable source installation. Standalone wheel
resource packaging, additional API adapters, automated legacy conversion and
real-library acceptance are not claimed by this parity table. None is silently
substituted with synthetic success.
