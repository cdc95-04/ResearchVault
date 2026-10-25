---
name: zotero-fetcher
description: Read existing Zotero parent items and attachments with explicit library identity, preserving exact parent and PDF keys.
---

# Zotero fetcher

Read [intake](../../references/intake.md) for the API boundary and
[evidence](../../references/evidence.md) for identity and missing-source states.

Resolve the requested library namespace and parent key using the official read
API. An explicit key that is missing or inconsistent must not silently fall back
to a title search. Enumerate attachments separately and identify main paper,
supplement, other file or unresolved role from available evidence.

Return observed metadata, parent zotero_key, distinct attachment pdf_key, source
availability and any version or collision issue. Do not invent a PDF path from a
key. Do not read or mutate Zotero's database directly. Reading a record is not
verification of its PDF content.

Reuse the exact resolved identity for subsequent Fulltext and Note work. Hand
missing-source acquisition to literature-acquisition only when requested; this
Skill does not create, replace, delete or annotate Zotero items.
