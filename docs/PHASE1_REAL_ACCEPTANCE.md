# Real intake acceptance procedure

This is a reusable acceptance procedure, not a report about an installation.
The historical filename is retained for existing documentation links. Keep each
run's actual identities, paths, hashes, inventories and logs outside version
control. Passing synthetic tests does not establish live Zotero integration.

## Scope and prerequisites

Choose one explicitly selected paper by DOI or exact arXiv version, an isolated
Vault and runtime, and an authorized Zotero target. Keep all three data locations
separate from the code repository and existing research records. A test Vault
does not make a Personal Library an isolated Zotero database.

Complete [read-only environment diagnostics](PHASE1_ENVIRONMENT_DIAGNOSTICS.md)
first. Record available metadata, version identity, lawful PDF route and complete
deduplication inventory. Review the `init` preview. Existing matching parents
and attachments must be reused; do not create duplicates to exercise a test.

Use the existing [intake commands and contracts](IDENTIFIER_INTAKE.md). Applied
operations require explicit authorization and a writable operation configuration.
Acquisition also needs its configured permission or per-operation `--enable`.
New Zotero items additionally require `--allow-zotero-create` and an existing
usable Local API write credential. No flag overrides the read-only guard.

## Keep reuse and creation coverage separate

| Acceptance path | Required observations | What it does not establish |
| --- | --- | --- |
| Existing-asset reuse | Exact parent and main attachment; fresh read-back; API MD5 and independently computed SHA-256; isolated archive and resume | New parent creation or file upload |
| New create and upload | Verified lawful PDF; durable parent intent and receipt; parent read-back; attachment intent/upload/read-back; independent file hashes | Scientific reading or human approval |
| Archive publication | New Fulltext and partial Note; reciprocal links; original source retained; validator passes | Semantic correctness of extracted prose, equations or figures |
| Resume | Same workflow identity; unchanged canonical assets; no extra Zotero mutations; frozen source provenance retained | Exactly-once behavior across independent concurrent clients |

Only claim the path actually executed. Missing credentials, unavailable services
or absent approval produce a blocked or not-run result, never a simulated PASS.

## Execute and independently verify

1. Record the starting configuration, inventory, source hashes and existing Vault
   file manifest in private operational storage. Do not export credential values.
2. Preview isolated `init`; verify containment and absence of overwrites. Apply
   only within the approved target and scope.
3. Run the selected intake. Enable acquisition and creation only if needed and
   authorized. The default generated Note must remain partial and human pending.
4. Open a new read-only Zotero client. Verify the namespace, original Server ID,
   exact parent, exact attachment, bibliographic identity and attachment role.
5. Obtain the attachment through the official `/file/view/url` endpoint. Compare
   independently computed MD5 to the API metadata and SHA-256 to the verified
   acquired or reused source. An HTTP success alone is insufficient.
6. Verify Fulltext extraction provenance, PDF/text hashes and reciprocal Note
   links. Run the formal CLI validator against the isolated configuration.
7. Repeat the ordinary request: expect `RESUME_REQUIRED`, without replacing
   records. Then run explicit `--resume`, and an equivalent canonical URL alias
   with `--resume`. Check actual file hashes, sizes, modification times, item
   identities and the request ledger, rather than relying on a `reused` label.
8. Restore the operation configuration to read-only, then perform final
   validation and preservation checks even when a preceding step failed.

Runtime events may append during resume. Canonical Fulltext and Note bytes must
not change. A changed user Note or conflicting source must stop the item rather
than being overwritten. Never directly read or modify `zotero.sqlite` for intake.

## Failure recovery matrix

| Condition | Required behavior | Safe acceptance method |
| --- | --- | --- |
| Uncertain external write | Keep the original durable intent; require reconciliation; no blind retry | Use isolated synthetic transports, or a separately approved disposable live target |
| Incomplete receipt | Reject unproven completion and preserve the receipt | Inspect namespace, Server ID, exact key and fresh read-back |
| Network interruption | Retain confirmed progress and failure reason | Separate pre-write connection failures from interrupted-write recovery |
| Duplicate identifier alias | Resolve to the same canonical workflow and receipt history | Repeat only the selected identifier and equivalent supported URL |
| Changed Server ID | Refuse cross-instance reuse | Use fixtures unless an isolated service-change test is explicitly authorized |
| Partial archive publication | Reuse staged hash-bound bytes; create only the missing member | Inject a failure in an isolated fixture; inspect both existing and missing records |

Do not force shutdowns, interrupt writes or modify a real library merely to
increase coverage. Label each unexercised live case `NOT_RUN`; fixture coverage
belongs in a separate column.

## Private run report

Record actual values locally for:

- Canonical paper identity and exact publication version.
- Library namespace, Server ID, parent key, attachment key and attachment role.
- PDF MD5/SHA-256, extracted-body hash, Fulltext/Note hashes and workflow identity.
- Durable receipt completion and independent read-back results.
- Validator diagnostics; initial run, ordinary repeat, explicit and alias resume.
- New parents, attachments, downloads, archive records and actual write counts.
- Source/configuration preservation and restored read-only state.
- Blocked and unexecuted cases, including the precise layer and minimal remedy.

Do not commit that report, its real keys, per-installation hashes, inventories,
original PDFs or screenshots. The repository contains the procedure and tests,
not evidence that every installation passed it. See [test coverage](IDENTIFIER_INTAKE_RESULTS.md)
and [archive quality requirements](PHASE1_1_ARCHIVE_QUALITY.md).
