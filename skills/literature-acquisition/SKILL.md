---
name: literature-acquisition
description: Obtain selected lawful paper PDFs, verify their publication identity and prepare controlled Zotero intake. Use after candidate selection.
---

# Literature acquisition

Read [intake](../../references/intake.md). Operate on an explicit list of selected
identities. Acquisition is disabled unless configured; credentials and downloads
stay outside the repository and Vault.

Prefer the configured lawful OA routes. Treat a returned URL as a location hint,
not proof of access rights or document identity. Check content type, usable PDF,
main-versus-supplement role, title/authors and publication/version evidence.
An incidental DOI in references does not verify the document. Preserve VERIFIED,
PROBABLE, AMBIGUOUS, SUPPLEMENT, WRONG and CORRUPTED outcomes separately; only a
VERIFIED main paper may become eligible for automatic intake.

Process the selected batch serially with durable per-item progress. Resume from
recorded state; do not redownload or rewrite blindly after an uncertain outcome.
Stop affected items at paywalls, login requirements, identity conflicts or damage
and report an actionable reason without bypassing access controls.

Before any authorized Zotero creation, read the target library and check for
duplicates. Preserve all existing items, annotations and attachments. Retain the
mutation-intent receipt and reconcile uncertain responses before retrying. Phase
one permits synthetic verification only; it does not authorize a real write.

Report obtained, unresolved and blocked items with their evidence. Hand verified
existing Zotero records to zotero-fetcher and source extraction to
fulltext-archiver; do not manufacture Paper Notes during acquisition.
