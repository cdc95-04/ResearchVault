# Archive artifact quality

This document describes the Note formatter's escaping contract, PDF extraction
limits and reproducible quality checks. It does not publish a user's artifacts,
source identifiers, extraction hashes or installation-specific acceptance report.

## Paper Note escaping

The original defect occurred at the HTML-entity/Markdown boundary in
`researchvault.notes._literal`. Sequential replacement processed newly generated
entities again: a backslash became `&#92;`, whose generated `#` then produced
`&&#35;92;`. HTML escaping followed by punctuation replacement also affected
brackets, underscores and apostrophe entities. YAML frontmatter and Fulltext
serialization were not the cause.

The formatter now encodes each original character exactly once. Generated
entities never re-enter the escaping pass. Literal source text such as `&#92;`
must display as that literal text after rendering, not as a decoded backslash.
Re-rendering deserialized raw metadata is supported; passing an already rendered
body back as raw source is not the round-trip contract.

Bare URLs and email addresses can also be auto-linked by a Markdown renderer
inside encoded metadata. Encoding `:`, `.` and `@` in the same character pass
keeps that untrusted source text literal. Authored Fulltext links are generated
separately. This is a source-encoding rule, not a keyword heuristic or a blind
replacement on the final document.

The regression tests cover raw strings, serialization, read-back and visible
literal text for paths, backslashes, Unicode, HTML, quotes, Markdown punctuation,
source entity strings and metadata. Scientific text expectations are retained;
entity spellings are not used as a substitute for displayed-text correctness.

## Markdown presentation acceptance

For a separate local rendering check, generate into a new isolated Vault. Use
an offline Markdown renderer and inspect both the rendered document and its DOM:

- Displayed source pointers equal raw frontmatter values.
- Displayed metadata JSON parses to the original provenance object.
- All seventeen canonical headings and authored Fulltext links remain present.
- Untrusted source content creates no unintended anchors, scripts, images,
  iframes or executable links.
- Long paths and metadata remain readable without losing characters.
- Compare a known defective fixture to verify the check can detect the defect.

Record renderer versions and screenshots only in private QA storage. Renderer
acceptance is distinct from testing the Obsidian application. Run the structural
validator separately for identity and reciprocal links.

## NUL and PDF font mapping

A PDF may map a nonzero character code to U+0000 through `/ToUnicode`. In that
case the extracted NUL can originate in source font mappings before ResearchVault
serializes anything. A printable visual glyph does not guarantee a correct
Unicode map, and another extractor's zero-NUL output is not semantic ground truth.

Use a read-only diagnosis to distinguish stages:

1. Hash the original PDF and existing Fulltext before inspection.
2. Count NULs by one-based extraction page and inspect extractor visitor output.
3. Inspect affected text operands, fonts, encodings, CMaps and Form XObjects.
   Distinguish source character code zero from a nonzero code mapped to U+0000.
4. Compare independently named outputs from another extractor and render the
   original affected pages. Record extractor versions and source/output hashes.
5. Check affected formulas and symbols visually; mark unresolved transcription
   or interpretation unverified. Font glyph names are diagnostic clues, not
   sufficient authority for automatic mathematical replacement.
6. Verify original PDF, Fulltext and historical hashes remain unchanged.

Reading order, clipping and hidden diagram text can differ between extractors.
Removing NULs or comparing whitespace-normalized sequences does not prove semantic
fidelity. Do not silently filter, replace or overwrite original evidence.

If a cleaned reading copy is needed, create an independent derived file with
the source hash, explicit transformation rules, before/after hashes and retained
diagnostics. It is not a replacement for canonical source evidence.

## Reproduction and acceptance boundary

The following tests use synthetic inputs and do not require a real paper or a
Zotero installation:

```sh
python -m unittest discover -s tests -p test_notes.py -v
python -m unittest discover -s tests -p test_fulltext_nul.py -v
python -m unittest discover -s tests -v
```

The NUL fixture maps a nonzero PDF character explicitly to U+0000 and includes
a printable-mapping control. It checks extraction, archive/re-read, source/text
hashes and reuse without filtering NULs. A portable full run must report actual
failures and platform capability skips separately; do not copy another machine's
test count or elapsed time as a current result.

For real regeneration, use the [isolated acceptance procedure](PHASE1_REAL_ACCEPTANCE.md),
an explicitly authorized target and a new output directory. Keep old records
unchanged, restore read-only configuration, and compare protected inputs before
and after. Formatter success and validator PASS do not establish complete
scientific reading, equation fidelity or human approval.
