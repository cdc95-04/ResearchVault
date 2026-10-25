"""Pure, source-bound Paper Note formatting; no reading or filesystem mutation.

An extraction is evidence of text availability, not a completed scientific
reading. Agent-supplied statements stay distinct from literal source excerpts,
and deterministic quote matching never certifies semantic entailment.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
from pathlib import PurePosixPath, PureWindowsPath
import re

from .identity import check_records


# Kept in parity with templates/paper.md, without requiring template filesystem
# access when this formatter is used from an installed package.
HEADINGS = (
    'Source and reading boundary',
    'Problem and evaluation setting',
    'Testable claims',
    'Contribution and comparison class',
    'System and information flow',
    'Proposed mechanism',
    'Physical dynamics and computation',
    'Self-model or body representation',
    'Data and learning procedure',
    'Baselines and controls',
    'Quantitative observations',
    'Discriminating tests',
    'Generalization boundary',
    'Failures and limitations',
    'Reproduction requirements',
    'Claim-to-source map',
    'Research implications',
)


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + ' must be nonempty text')
    if any(ord(character) < 32 and character not in '\t\r\n' for character in value):
        raise ValueError(field + ' contains control characters')
    return value


def _words(value):
    return ' '.join(value.split())


def _literal(value):
    """Render arbitrary source/agent text without creating authored links/HTML."""
    # Escape each source character once. Revisiting generated entities would
    # escape their '#' (including the apostrophe entity from html.escape).
    # Keep URLs/email literal too: GFM autolinks can consume adjacent entities
    # such as encoded JSON delimiters and corrupt the displayed provenance.
    return ''.join('&#' + str(ord(character)) + ';'
                   if character in '\\[]()*_`#|:.@' else html.escape(character, quote=True)
                   for character in _words(str(value)))


def _relative(value, field):
    value = _text(value, field)
    path = PurePosixPath(value)
    if ('\\' in value or ':' in value or path.is_absolute()
            or any(part in ('', '.', '..') for part in value.split('/'))
            or not value.endswith('.md')
            or any(character in value for character in '[]|#\r\n<>')):
        raise ValueError(field + ' must be an unambiguous Vault-relative Markdown path')
    return value


def _hash(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise ValueError(field + ' must be a lowercase SHA-256 digest')
    return value


def _analysis(value, pdf_sha256, pages):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('analysis must be an object or null')
    if set(value) - {'pdf_sha256', 'facts', 'interpretations', 'hypotheses'}:
        raise ValueError('analysis contains unsupported fields')
    if value.get('pdf_sha256') != pdf_sha256:
        raise ValueError('analysis PDF SHA-256 does not match the selected source')
    result = {'pdf_sha256': pdf_sha256}
    for field in ('facts', 'interpretations', 'hypotheses'):
        rows = value.get(field, [])
        if not isinstance(rows, list):
            raise ValueError('analysis.' + field + ' must be a list')
        result[field] = []
        for row in rows:
            if field != 'facts':
                result[field].append(_text(row, 'analysis.' + field))
                continue
            if not isinstance(row, dict) or set(row) != {'statement', 'quote', 'page_index'}:
                raise ValueError('Each fact needs statement, quote and page_index only')
            statement = _text(row['statement'], 'fact.statement')
            quote = _text(row['quote'], 'fact.quote')
            page = row['page_index']
            if type(page) is not int or not 1 <= page <= len(pages):
                raise ValueError('fact.page_index must address a real 1-based extraction page')
            if _words(quote) not in _words(pages[page - 1]):
                raise ValueError('fact.quote is absent from its selected extraction page')
            result[field].append({'statement': statement, 'quote': quote, 'page_index': page})
    if not any(result[field] for field in ('facts', 'interpretations', 'hypotheses')):
        raise ValueError('analysis must contain at least one source excerpt, interpretation or hypothesis')
    return result


def render(identity: dict, *, note_path, fulltext_path, pdf_path, pdf_sha256,
           pages: list[str], metadata_sources: list[dict], analysis: dict | None = None,
           synthetic=False) -> dict:
    """Format a partial Note and analysis handoff from explicitly supplied inputs.

    Callers bind ``pages`` to the parsed PDF bytes and check resolved filesystem
    containment. This function performs no PDF parsing, I/O or scientific
    inference. A fact quote is checked only against its 1-based extraction page;
    its accompanying agent statement is always an interpretation.
    """
    if not isinstance(identity, dict):
        raise ValueError('identity must be an object')
    check_records([identity])
    _text(identity.get('title'), 'identity.title')
    if not identity.get('pdf_key'):
        raise ValueError('A Note requires an exact PDF attachment key')
    note_path = _relative(note_path, 'note_path')
    fulltext_path = _relative(fulltext_path, 'fulltext_path')
    if note_path == fulltext_path:
        raise ValueError('Note and Fulltext must be different records')
    pdf_path = _text(pdf_path, 'pdf_path')
    if not (PurePosixPath(pdf_path).is_absolute() or PureWindowsPath(pdf_path).is_absolute()):
        raise ValueError('pdf_path must name an absolute external source')
    pdf_sha256 = _hash(pdf_sha256, 'pdf_sha256')
    if not isinstance(pages, list) or not pages or any(not isinstance(page, str) for page in pages):
        raise ValueError('pages must be a nonempty list of extraction text strings')
    if not any(page.strip() for page in pages):
        raise ValueError('Extraction contains no text; a Note cannot imply text availability')
    if not isinstance(metadata_sources, list) or any(not isinstance(row, dict) for row in metadata_sources):
        raise ValueError('metadata_sources must be a list of provenance objects')
    if type(synthetic) is not bool:
        raise ValueError('synthetic must be Boolean')
    try:
        # Reject cyclic values, nonfinite numbers and non-JSON provenance before
        # returning data that a caller could publish as YAML.
        source_json = json.dumps(metadata_sources, ensure_ascii=False, sort_keys=True, allow_nan=False)
        sources = json.loads(source_json)
    except (TypeError, ValueError) as exc:
        raise ValueError('metadata_sources must contain finite JSON provenance') from exc
    captured = _analysis(analysis, pdf_sha256, pages)
    status = 'AGENT_ANALYSIS_CAPTURED' if captured is not None else 'ANALYSIS_PENDING'
    body_text = '\n\n'.join(pages)
    text_sha256 = hashlib.sha256(body_text.encode('utf-8')).hexdigest()
    data = {field: copy.deepcopy(identity.get(field)) for field in
            ('title', 'library_id', 'zotero_key', 'pdf_key', 'doi', 'arxiv_id')}
    data = {'schema_version': 2, 'type': 'literature-note', **data,
            'fulltext_path': fulltext_path, 'pdf_path': pdf_path, 'status': 'draft',
            'read_status': 'partial', 'evidence_status': 'unverified', 'claim_ids': [],
            'synthetic': synthetic, 'human_review_status': 'pending',
            'analysis_status': status, 'pdf_sha256': pdf_sha256,
            'text_sha256': text_sha256, 'metadata_sources': sources}
    sections = {index: ['[unverified] Pending source-grounded reading; no scientific finding is inferred.']
                for index in range(1, 18)}
    sections[1] = [
        'Bibliographic metadata facts come from the supplied identity and provenance objects; '
        'they do not establish the scientific claims of the paper.',
        'Title: ' + _literal(identity['title']) + '.',
        'Exact identity: library_id=' + _literal(identity.get('library_id'))
        + '; zotero_key=' + _literal(identity['zotero_key'])
        + '; pdf_key=' + _literal(identity['pdf_key']) + '.',
        'Original PDF source pointer: ' + _literal(pdf_path) + '.',
        'PDF SHA-256: ' + pdf_sha256 + '.',
        'Original extraction: [[' + fulltext_path + ']]; text SHA-256: ' + text_sha256
        + '; extracted pages: ' + str(len(pages)) + '.',
        'Source layers supplied: bibliographic metadata, PDF identity/hash and page extraction. '
        'This formatter has not visually inspected the PDF or performed scientific reading. '
        'Extraction page indices are 1-based parser positions, not observed printed page numbers. '
        'Tables, figures, mathematical layout, supplementary material and extraction completeness remain unverified.',
        'Analysis state: ' + status + '; human review: pending; reading remains partial.',
        'Metadata provenance: ' + (_literal(source_json) if sources else '[unverified] No metadata provenance supplied.'),
    ]
    sections[3] = [
        '### 论文源文 / Paper-source excerpts',
        'Literal quotations below, when supplied, are checked against the selected extracted page. '
        'The label fulltext_verified applies only to literal text presence. '
        'It does not certify a statement\'s semantic entailment or visual PDF verification.',
    ]
    sections[6] = ['### 模型分析 / Model interpretation',
                   'Agent interpretations are analytical suggestions; the paper does not itself establish them.']
    sections[16] = ['Every excerpt retains the exact Fulltext, PDF hash and extraction page index. '
                    'Agent paraphrases and hypotheses retain separate labels; semantic entailment is unverified.']
    sections[17] = ['### 待验证假设 / Unverified hypotheses',
                    'Hypotheses are speculative follow-up ideas and do not establish a research gap.']
    facts = captured['facts'] if captured else []
    interpretations = captured['interpretations'] if captured else []
    hypotheses = captured['hypotheses'] if captured else []
    for index, fact in enumerate(facts, 1):
        label = 'E' + str(index)
        sections[3].append(label + ' [fulltext_verified; text-only] Extraction page index '
                           + str(fact['page_index']) + ': ' + _literal(fact['quote']))
        sections[3].append(label + ' agent statement [interpretation; entailment unverified]: '
                           + _literal(fact['statement']))
        sections[16].append(label + ': literal excerpt [fulltext_verified; text-only]; agent statement '
                            '[interpretation]; source [[' + fulltext_path + ']], extraction page index '
                            + str(fact['page_index']) + ', PDF SHA-256 ' + pdf_sha256 + '.')
    if not facts:
        sections[3].append('[unverified] No source-checked scientific excerpt has been supplied.')
        sections[16].append('[unverified] No scientific claim-to-source map has been completed.')
    for index, statement in enumerate(interpretations, 1):
        sections[6].append('A' + str(index) + ' [interpretation]: ' + _literal(statement))
    if not interpretations:
        sections[6].append('[unverified] Model analysis has not been supplied.')
    for index, statement in enumerate(hypotheses, 1):
        sections[17].append('H' + str(index) + ' [speculative]: ' + _literal(statement))
    if not hypotheses:
        sections[17].append('[unverified] No follow-up hypothesis has been supplied.')
    sections[11] = ['[unverified] Quantitative results, units, denominators, conditions and uncertainty '
                    'have not been independently assessed by this formatter. Any supplied excerpt remains '
                    'bounded by its literal text presence and source locator in sections 3 and 16.']
    sections[14] = ['[unverified] Author-reported failures and reader-inferred concerns remain to be '
                    'distinguished during source-grounded reading. No absence of failures is inferred.']
    body = '\n# Paper Note\n\n' + '\n\n'.join(
        '## ' + str(index) + '. ' + heading + '\n\n' + '\n\n'.join(sections[index])
        for index, heading in enumerate(HEADINGS, 1)) + '\n'
    handoff = {
        'status': status, 'identity': copy.deepcopy({field: data[field] for field in
            ('library_id', 'zotero_key', 'pdf_key', 'doi', 'arxiv_id', 'title')}),
        'note_path': note_path, 'fulltext_path': fulltext_path, 'pdf_path': pdf_path,
        'pdf_sha256': pdf_sha256, 'text_sha256': text_sha256, 'extraction_page_count': len(pages),
        'human_review_status': 'pending', 'read_status': 'partial',
        'required_workflow': 'skills/paper-note-writer/SKILL.md',
        'reading_boundary': 'Supplied extraction only; visual PDF and scientific entailment unverified.',
        'remaining_work': ['Inspect the exact bound sources and the seventeen reading checks.',
                           'Separate source statements, agent interpretations and speculative hypotheses.',
                           'Retain real locators, units, denominators and missing evidence.',
                           'Propose a diff before changing an existing Note; do not overwrite it.'],
        'analysis': copy.deepcopy(captured),
    }
    return {'data': data, 'body': body, 'analysis_status': status, 'handoff': handoff}
