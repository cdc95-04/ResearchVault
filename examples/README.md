# Synthetic examples

This small Vault contains six independently authored draft records. It uses
invented fixture identities and contains no publication DOI, paper PDF, original
extraction, measured result or quoted paper passage. All records are labeled
synthetic and agent-curated. Their purpose is to demonstrate honest partial
states and links, not to benchmark real scientific reading.

The three reading targets concern physical reservoir computing, self-models and
robot learning. They are exercise descriptions rather than summaries of real
papers. A Concept, Question and Hypothesis connect those targets while remaining
speculative. No Research Gap, Claim Lock or experimental conclusion is asserted.

Use the explicit configuration `examples/synthetic.yaml` from the repository's
documented CLI. Its relative Vault root resolves from that configuration's
directory and synthetic mode is deliberately true. When specifying the Vault
directly, also supply `--synthetic`. Real use must choose a root outside the code
checkout and must not repurpose these fixture identifiers as actual Zotero keys.

Validation is expected to report missing PDFs and Fulltext counterparts for the
three partial Notes. Those warnings are intentional evidence gaps; they must
not be silenced by changing read_status to complete or fabricating sources.
The associated records should still have no structural errors.

The reusable source templates live only in the repository's templates/ directory.
This example Vault does not maintain a second copied template collection.
