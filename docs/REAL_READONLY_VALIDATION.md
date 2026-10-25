# Read-only validation guide

This guide defines reusable checks and their evidence limits. It contains no
installation inventory, user record counts, private file hashes or machine
capability results. Store each run's observations in private, ignored storage.

## Select the inspection boundary

For ordinary ResearchVault and Zotero intake checks, use the configured Local
API and the formal validator:

```sh
python -m researchvault --read-only --config config/local.yaml zotero-inventory
python -m researchvault --read-only --config config/local.yaml validate
```

Configure an explicit external Vault first; never point a real Vault at the code
repository or an unrelated Obsidian Vault. Personal Library uses `users/0` with
`library_id: null`; group libraries require an explicit group identity. If the
API is unavailable, report that state instead of using a database fallback or
claiming an empty library. See [environment diagnostics](PHASE1_ENVIRONMENT_DIAGNOSTICS.md).

An empty complete library or Vault is a valid observation, not a software
failure. It does not test nonempty identity, attachment or record handling.
Record unavailable coverage separately from failed checks. Structural validation
does not establish complete reading, scientific truth or human review.

## Read-only guard

`--read-only` and `read_only: true` are explicit protections. A later false
command-line default cannot disable a configured true value. Write-capable
entrypoints reject applied initialization, archiving, batch ingestion,
acquisition and receipt creation before side effects. The Zotero client's
read-only mode rejects non-GET requests and applied creation/import before a
transport call or mutation-intent receipt is created.

Evaluation may print to stdout in read-only mode; writing its output file is
blocked. The validator retains diagnostic codes, severity and counts while
withholding untrusted free-text detail and external absolute paths in read-only
reports. This redaction is not permission to publish inventories or arbitrary
stdout without inspection.

## Optional offline source-inspection harness

`scripts/validate_environment.py` is a separately selected, read-only inspection
tool. It is not part of identifier intake and must not be invoked as an automatic
fallback when the Local API is unavailable. If the operator explicitly selects
this offline inspection, its source-path arguments remain local:

```sh
python scripts/validate_environment.py --zotero-data ZOTERO_DATA_ROOT --vault VAULT_ROOT --workspace .qa/environment
```

Replace the uppercase placeholders with authorized roots. The harness restricts
private output to ignored `.qa/` or operating-system temporary storage, rejects
overlap with protected source roots, copies database components as binary reads
into a new isolated directory, and verifies source fingerprints around the copy.
Only the copy is opened through SQLite `mode=ro` and `query_only`, with an
authorizer limited to reads. No source database is modified.

The Vault inspector walks without following reparse directories, reads existing
files and compares inspected file manifests before and after. It does not invoke
init, create Notes, migrate, rename, delete or edit `.obsidian`. File-fingerprint
preservation concerns content and recorded metadata, not access-time bookkeeping.

The generated aggregate summary and separate private inventory are operational
artifacts. Never commit either database copies or inventories. A schema validator
only applies to ResearchVault records; arbitrary Obsidian notes are not silently
converted into such records.

## Coverage and portability

Check and report these dimensions separately:

| Dimension | Evidence to record locally |
| --- | --- |
| Library read | Actual namespace, complete pagination and observed item count |
| Identity and attachments | Exact stable keys, DOI/arXiv consistency, missing or multiple PDFs |
| Existing records | Frontmatter, canonical identifiers, reciprocal links and collisions |
| Preservation | Before/after source fingerprints and zero unauthorized writes |
| Containment | Traversal and symlink/junction escape handling |
| Platform capability | Supported native links, path lengths, Unicode and spaces |
| Privacy | Local config ignored; no secret, source database, PDF or private path published |

Synthetic fixtures exercise cases absent from the selected real environment.
Their coverage must be labelled synthetic. A platform skip is not a pass on that
platform, and a successful CI matrix does not supply missing real library data.

```sh
python -m unittest discover -s tests -v
python scripts/audit_repository.py
python scripts/audit_plugin.py
python -m pip check
```

Use [real intake acceptance](PHASE1_REAL_ACCEPTANCE.md) for an independently
authorized write/reuse round. No result from this read-only guide establishes
new parent creation, PDF upload or recovery after an uncertain external write.
