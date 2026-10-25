---
name: ingest-orchestrator
description: Coordinate an explicitly selected, bounded batch through existing Zotero, Fulltext and Paper Note stages while preserving per-item state.
---

# Ingest orchestrator

Read [intake](../../references/intake.md) for batch state. Load another Skill's
instructions only when that stage is actually needed. This is bounded workflow
coordination, not an autonomous research or discovery service.

Use the user-selected identities and requested end state. Inspect existing
records before scheduling work. For each item record identity resolution,
attachment availability, extraction availability, Note state and the next
permitted action. Reuse verified artifacts and stop only affected conflicting
items. Do not silently expand the batch from a search result.

Route existing-library reads to zotero-fetcher, original text to
fulltext-archiver and analysis to paper-note-writer. External discovery and lawful
acquisition are separate stages only when included in scope. Ingest itself does
not invent analytical Notes or mark unread work complete.

Keep resumable progress and reasons for partial/failed items. Reconcile uncertain
external mutation outcomes before retrying. Respect phase-one synthetic limits.
Report completed stages, reused artifacts, unresolved items and the actual batch
boundary. A workflow stopped at missing evidence is a partial result, not an
excuse to fabricate the next layer.
