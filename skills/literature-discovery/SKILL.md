---
name: literature-discovery
description: Find external publication candidates and verify metadata identity for a specified research question. Use before acquisition, not for searching an existing Vault.
---

# Literature discovery

Return a bounded candidate set with the exact queries, sources, search times and
unresolved identity conflicts. Read [intake](../../references/intake.md) and use
the [candidate template](../../templates/candidate.md) only when saving records.

Establish the user's topic, date/version limits and purpose from the request.
Search distinct terminology when it changes recall; preserve the actual query
and source for each candidate. Resolve DOI/arXiv identities from source metadata,
including versions and relations. A title can suggest a match but cannot become
the canonical identifier. Explicit conflicting identifiers remain unresolved.

Deduplicate confirmed identities without collapsing different publication
versions. Describe relevance as a selection judgment based on what was inspected.
Do not report a finding, PDF verification or complete coverage from metadata.
Keep selected_for_acquisition false unless selection was authorized.

Hand selected identities to literature-acquisition when requested. For a formal
search protocol and coverage accounting, use systematic-literature-review. Stop
after the requested discovery scope; this Skill does not acquire PDFs or write
to Zotero.
