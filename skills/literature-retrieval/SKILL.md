---
name: literature-retrieval
description: Search the current Vault's Paper Notes and Knowledge, with disclosed supplementary Fulltext recall when needed.
---

# Literature retrieval

Read [evidence](../../references/evidence.md). Establish the explicit Vault and
the user's conceptual or identity query. Search Notes and Knowledge first.
Include Fulltext when requested or when Note recall is empty; disclose that
change and distinguish raw matches from analyzed evidence.

The `retrieve` command is a lexical candidate-recall primitive: it requires all
query tokens as case-insensitive substrings and returns traversal order, not
semantic relevance rank. For a conceptual question, preserve the original query,
interpret the requested relation, and make bounded additional lexical calls
with shorter source terms or concept expansions. Record those queries and
deduplicate before inspecting evidence. A word match is not an answer.

Keep exact aliases distinct from related, broader, narrower and contrast
concepts. Existing Knowledge may guide expansion when its sources support the
relation. Physical reservoir computing and morphological computation can relate
without being equivalent; a robot self-model is not automatically a body schema
or a state estimator. General world models, World Action Model (WAM),
vision-language-action (VLA) and embodied intelligence describe different scopes.
Use [reading boundaries](../../references/reading.md) when resolving these
relations; do not turn related terms into interchangeable synonyms.

Report actual searched layers, matched records and unique namespaced parent
identities. Multiple attachments or matching paragraphs from one paper do not
increase the paper count. Surface unread sources, absent Fulltext, broken links
and unresolved identities relevant to the answer.

Answer from the inspected records with paths and evidence limits. Do not report
complete field coverage, impose a fixed paper quota or quietly search externally.
If local evidence cannot answer the question, describe the missing evidence and
hand external work to literature-discovery only when within the user's request.
