# Identifier intake verification guide

This document describes the shipped regression coverage and how to record a new
run. It does not contain a machine-specific test report or claim that a particular
library, publisher, operating system or credential is currently available.

## Automated coverage

| Test modules | Behavior exercised |
| --- | --- |
| `test_resolution.py` | Supported identifiers, aliases, canonical metadata and exact version boundaries |
| `test_pdf_identity.py` | Source response/PDF binding, official routes, wrong publication/version and supplement rejection |
| `test_notes.py` | Seventeen-section partial Notes, evidence labels, source bindings, literal escaping and read-back |
| `test_fulltext_nul.py` | Source font mapping, extraction and archival preservation without NUL filtering |
| `test_zotero.py` | Inventory, exact attachment reads, guarded creation, upload, receipts and read-back |
| `test_identifier_intake.py` | Bounded selected-item orchestration, lawful PDF handling, dedup, archive linkage and reuse |
| `test_intake_recovery.py` | Uncertain receipts, identifier aliases, namespace/Server ID changes and interrupted publication |
| `test_identifier_cli.py` | Production parser/dispatcher, dry-run/apply/resume and error boundaries |
| Existing core/read-only/validation suites | Containment, source preservation, configuration guards and scientific record contracts |

The end-to-end fixture invokes production parsers, PDF verification/extraction,
Zotero client and receipt handling, archive publication and validation. External
public/Local API transports use synthetic responses and documents. These tests
exercise integration logic; they do not establish live publisher availability,
real Zotero-write acceptance or a scientist's reading judgment.

## Reproduce in a prepared environment

From the repository, with the documented runtime and PDF dependencies installed:

```sh
python -m unittest discover -s tests -v
python scripts/audit_repository.py
python scripts/audit_plugin.py
python -m researchvault --config examples/synthetic.yaml validate
python scripts/validate_golden.py --check-inputs
python scripts/semantic_contract.py --sac-revision
python scripts/benchmark_retrieval.py --check-recorded
python -m pip check
python scripts/audit_dependencies.py
```

Dependency vulnerability auditing requires the audit tooling and network service
specified by [CI](../.github/workflows/ci.yml). A network failure is not a clean
security result. Dependency constraints live in [pyproject.toml](../pyproject.toml);
do not treat a previous audit as assurance about today's installed environment.

The example Vault intentionally contains partial synthetic Notes without PDFs or
Fulltext counterparts. Its expected warnings are described in [examples](../examples/README.md).
The Golden and recorded retrieval checks validate frozen contracts/accounting;
they do not rerun independent scientific review or promote human review status.

When native symlink, junction, hard-link or long-path behavior is unavailable,
retain the actual skip/failure and its reason. Do not emulate a successful host
operation and report it as native acceptance. Use an explicitly chosen writable
temporary location when necessary; keep its actual path out of shared logs.

## Record actual results privately

For each new run, retain command, exit status, test totals, failures, skips and
relevant tool versions in ignored operational storage. Separate:

- Unit and fixture integration results.
- Repository/resource/privacy checks.
- Dependency consistency and vulnerability checks.
- Hosted CI results for each tested platform and Python version.
- Real-service acceptance, including blocked and not-run cases.

Do not copy counts, elapsed time or platform outcomes from another installation.
A local run does not imply hosted CI passed, and CI does not prove real-library
interoperability. Review publication material for private paths and identifiers;
the repository hygiene scanner is a heuristic, not a complete secret detector.

## Live acceptance remains separate

Follow [environment diagnostics](PHASE1_ENVIRONMENT_DIAGNOSTICS.md) and the
[real intake acceptance procedure](PHASE1_REAL_ACCEPTANCE.md) for a controlled
real run. An existing-item reuse test does not exercise parent creation/upload.
Actual creation is accepted only after independently verified parent and
attachment read-back, MD5/SHA-256 checks and durable receipt completion.

Successful archival still produces a partial, human-pending Note unless a
separate scientific reading process supplies reviewed content. Source extraction,
structural validator PASS and preserved hashes are necessary evidence controls;
they do not prove every formula, mechanism or interpretation correct.
