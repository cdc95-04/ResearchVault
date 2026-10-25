"""Read-only record checks. Consistency is not a scientific truth judgment."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path, PureWindowsPath
import re
import hashlib

from .documents import diagnostic, load_yaml, read_record, record_paths
from .identity import check_records

EVIDENCE = {'pdf_verified', 'fulltext_verified', 'note_supported', 'derived', 'interpretation', 'speculative', 'unverified'}
VERIFIED = {'pdf_verified', 'fulltext_verified'}


def reference(settings, value, records):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.removeprefix('[[').removesuffix(']]').split('|', 1)[0].split('#', 1)[0]
    candidates = {text, text + '.md'}
    direct = [record for record in records if record.relative in candidates]
    if direct:
        return direct[0] if len(direct) == 1 else None
    if '/' in text or '\\' in text or ':' in text or text in ('.', '..'):
        return None
    named = [record for record in records if record.path.stem == text or record.data.get('title') == text]
    return named[0] if len(named) == 1 else None


def _source_path(settings, value):
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    try:
        return path.resolve() if path.is_absolute() else settings.resolve(value)
    except ValueError:
        return None


def _words(value):
    return ' '.join(str(value).split())


def verify_claim(settings, claim, records):
    """Validate source bindings and exact excerpts without inferring entailment."""
    issues = []
    location = claim.get('page_path', claim.get('claim_id', 'claim'))
    def flag(code, detail):
        issues.append(diagnostic(code, location, detail))
    rows = claim.get('source_notes', [])
    if not isinstance(rows, list):
        flag('SOURCE_MISMATCH', 'source_notes must be a list of actual Note references')
        rows = []
    notes = [reference(settings, path, records) for path in rows]
    if any(record is None or record.type != 'literature-note' for record in notes):
        flag('SOURCE_MISMATCH', 'Every declared source Note must resolve')
    notes = [record for record in notes if record and record.type == 'literature-note']
    if claim.get('evidence_status') not in (None, 'unverified', 'speculative') and not notes:
        flag('SOURCE_MISMATCH', 'A supported claim needs actual source Notes')
    declared = claim.get('source_papers')
    if declared is not None and (not isinstance(declared, list) or any(not isinstance(k, str) for k in declared)
                                or set(declared) != {n.data.get('zotero_key') for n in notes if isinstance(n.data.get('zotero_key'), str)}):
        flag('SOURCE_MISMATCH', 'Declared paper keys must match the linked source Notes')
    verified = isinstance(claim.get('evidence_status'), str) and claim['evidence_status'] in VERIFIED
    entries = claim.get('verification', [])
    if not isinstance(entries, list):
        flag('INVALID_VERIFICATION', 'verification must be a list')
        return issues
    if verified and not entries:
        flag('EVIDENCE_RECORD_REQUIRED', 'A verified assertion needs source-level verification records')
    for entry in entries:
        if not isinstance(entry, dict):
            flag('INVALID_VERIFICATION', 'Source verification must be an object')
            continue
        fulltext = reference(settings, entry.get('fulltext_path'), records)
        matching = [n for n in notes if n.data.get('zotero_key') == entry.get('zotero_key')]
        if entry.get('zotero_key') is None and fulltext:
            matching = [n for n in notes if n.data.get('zotero_key') == fulltext.data.get('zotero_key')]
        if len(matching) != 1:
            flag('SOURCE_MISMATCH', 'Verification must resolve to exactly one declared source Note')
            continue
        note = matching[0]
        if 'library_id' in entry and entry['library_id'] != note.data.get('library_id'):
            flag('SOURCE_MISMATCH', 'Verification library differs from the source Note')
            continue
        bound = reference(settings, note.data.get('fulltext_path'), records)
        if fulltext is None or bound != fulltext:
            flag('SOURCE_MISMATCH', 'Verification must use the Fulltext linked by its source Note')
            continue
        if fulltext:
            if fulltext.type != 'literature-fulltext' or any(fulltext.data.get(k) != note.data.get(k) for k in ('zotero_key', 'pdf_key', 'library_id')):
                flag('SOURCE_MISMATCH', 'Fulltext and Note identities disagree')
                continue
        if entry.get('pdf_key') is not None and entry['pdf_key'] != note.data.get('pdf_key'):
            flag('SOURCE_MISMATCH', 'Verification attachment differs from the source Note')
        quote = entry.get('quote')
        locator = entry.get('locator', {})
        if not isinstance(locator, dict):
            flag('INVALID_LOCATOR', 'locator must be an object')
            continue
        page = locator.get('pdf_page')
        direct_pdf = claim.get('evidence_status') == 'pdf_verified' or entry.get('method') == 'pdf' or page is not None
        if verified and direct_pdf and not quote and not (type(page) is int and isinstance(entry.get('observation'), str) and entry['observation'].strip()):
            flag('EVIDENCE_RECORD_REQUIRED', 'PDF verification needs an exact excerpt or a page-bound explicit observation')
        if direct_pdf:
            path = _source_path(settings, entry.get('pdf_path') or note.data.get('pdf_path'))
            original = _source_path(settings, note.data.get('pdf_path'))
            if path is None or not path.is_file() or original is None or path != original:
                flag('PDF_UNAVAILABLE', 'Exact source PDF is required for page/visual verification')
                continue
            try:
                from pypdf import PdfReader
                reader = PdfReader(path)
                if page is not None and (type(page) is not int or not 1 <= page <= len(reader.pages)):
                    flag('FABRICATED_PAGE', 'PDF page locator is outside the actual document')
                    continue
                selected = [reader.pages[page - 1]] if page is not None else reader.pages
                source = '\n'.join(p.extract_text() or '' for p in selected)
            except Exception as exc:
                flag('PDF_UNCHECKED', f'PDF check could not complete: {type(exc).__name__}')
                continue
        elif fulltext:
            source = fulltext.body
        else:
            flag('FULLTEXT_UNAVAILABLE', 'Verified text must point to an existing Fulltext record')
            continue
        if verified and not direct_pdf and not quote:
            flag('EVIDENCE_RECORD_REQUIRED', 'Verified text needs an exact source excerpt')
        if quote is not None and (not isinstance(quote, str) or not quote.strip() or _words(quote) not in _words(source)):
            flag('FABRICATED_QUOTE', 'Quoted passage is not present in the selected original source')
    return issues


def _links(settings, record, records):
    # Fulltext bodies preserve source extraction, where math and citations can
    # resemble Markdown links. Their machine-readable source links are checked
    # separately; only authored record bodies have Vault navigation semantics.
    if record.type == 'literature-fulltext':
        return []
    issues = []
    for match in re.finditer(r'(!?)\[\[([^\]\n]+)\]\]|(!?)\[[^\]\n]*\]\(([^)\n]+)\)', record.body):
        wiki = match.group(2)
        raw = (wiki or match.group(4)).strip('<>').split('|', 1)[0]
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', raw) or raw.startswith('#'):
            continue
        plain = raw.split('#', 1)[0]
        if wiki and reference(settings, plain, records):
            continue
        if not wiki:
            target = (record.path.parent / plain).resolve()
            if target.is_relative_to(settings.vault) and target.is_file():
                continue
        else:
            try:
                if settings.resolve(plain).is_file():
                    continue
            except ValueError:
                pass
        issues.append(diagnostic('BROKEN_LINK', record.relative, raw))
    return issues


def _readonly_report(settings, result):
    """Keep diagnostic codes useful without exporting private source details."""
    if not settings.read_only:
        return result
    diagnostics = []
    for issue in result['diagnostics']:
        path = str(issue['path'])
        try:
            if Path(path).is_absolute():
                path = 'Vault' if Path(path).resolve() == settings.vault else settings.relative(path)
            elif PureWindowsPath(path).drive or path.startswith(('\\', '/')):
                path = 'external-source'
            else:
                path = settings.relative(settings.resolve(path))
        except (ValueError, OSError):
            path = 'external-source'
        diagnostics.append({**issue, 'path': path,
                            'detail': 'Details withheld in read-only validation to protect source content.'})
    return {**result, 'diagnostics': diagnostics}


def validate(settings):
    issues, records = [], []
    if not settings.vault.is_dir():
        return _readonly_report(settings, {'valid': False, 'diagnostics': [diagnostic('VAULT_MISSING', settings.vault, 'Selected Vault does not exist')], 'errors': 1, 'warnings': 0, 'records': 0})
    try:
        for path in record_paths(settings):
            try:
                records.append(read_record(path, settings.vault))
            except (ValueError, OSError) as exc:
                issues.append(diagnostic('INVALID_RECORD', path.relative_to(settings.vault), exc))
    except ValueError as exc:
        issues.append(diagnostic('PATH_ESCAPE', settings.vault, exc))
    library = settings.options['zotero']['library_id']
    sources = [record for record in records if record.type in ('literature-note', 'literature-fulltext')]
    try:
        check_records([record.data for record in sources])
    except ValueError as exc:
        issues.append(diagnostic('IDENTITY_CONFLICT', 'Vault', exc))
    by_type_key = defaultdict(list)
    for record in sources:
        if isinstance(record.data.get('zotero_key'), str):
            by_type_key[(record.type, record.data['zotero_key'])].append(record)
        if record.data.get('library_id') != library:
            issues.append(diagnostic('LIBRARY_MISMATCH', record.relative, 'Source belongs to a different library'))
    for group in by_type_key.values():
        if len(group) > 1:
            issues.append(diagnostic('DUPLICATE_SOURCE', group[0].relative, 'Multiple records for one parent and layer'))
    claims, claim_ids = [], set()
    claim_root = settings.folder('metadata') / 'claims'
    for path in sorted(claim_root.glob('*')):
        if path.suffix.lower() not in ('.yaml', '.yml', '.json'):
            continue
        try:
            settings.resolve(settings.relative(path))
            claim = load_yaml(path.read_text(encoding='utf-8-sig'))
            if not isinstance(claim, dict) or not isinstance(claim.get('claim_id'), str) or not claim['claim_id']:
                raise ValueError('Claim sidecar needs a nonempty claim_id')
            if claim['claim_id'] in claim_ids:
                raise ValueError('Duplicate claim_id')
            claim_ids.add(claim['claim_id'])
            claims.append((settings.relative(path), claim))
        except (ValueError, OSError) as exc:
            issues.append(diagnostic('INVALID_CLAIM', path, exc))
    for record in records:
        data = record.data
        complete = str(data.get('read_status', data.get('status', ''))).casefold() in ('complete', 'completed', 'ready')
        strict = complete or str(data.get('evidence_status')) in VERIFIED
        if data.get('schema_version') != 2:
            issues.append(diagnostic('SCHEMA_VERSION', record.relative, 'Expected Vault record schema 2'))
        ids = data.get('claim_ids', [])
        if not isinstance(ids, list):
            issues.append(diagnostic('CLAIM_LIST', record.relative, 'claim_ids must be a list'))
        else:
            for cid in ids:
                if not isinstance(cid, str) or cid not in claim_ids:
                    issues.append(diagnostic('CLAIM_MISSING', record.relative, 'Important claim has no provenance sidecar'))
        if record.type in ('literature-note',) or str(record.type).startswith(('knowledge-', 'research-gap', 'research-hypothesis')):
            status = data.get('evidence_status')
            if not isinstance(status, str) or status not in EVIDENCE:
                issues.append(diagnostic('EVIDENCE_STATE', record.relative, 'Unknown or absent literature evidence label'))
        if record.type in ('literature-note', 'literature-fulltext'):
            other_type = 'literature-fulltext' if record.type == 'literature-note' else 'literature-note'
            link_name = 'fulltext_path' if record.type == 'literature-note' else 'note_path'
            other = reference(settings, data.get(link_name), records)
            if other is None:
                issues.append(diagnostic('MISSING_COUNTERPART', record.relative, f'{link_name} is unavailable', 'error' if strict else 'warning'))
            elif other.type != other_type or any(data.get(k) != other.data.get(k) for k in ('zotero_key', 'pdf_key', 'library_id')):
                issues.append(diagnostic('SOURCE_MISMATCH', record.relative, 'Linked evidence belongs to a different source'))
            elif reference(settings, other.data.get('note_path' if link_name == 'fulltext_path' else 'fulltext_path'), records) != record:
                issues.append(diagnostic('RECIPROCAL_LINK', record.relative, 'Counterpart must link back to this record'))
            pdf = _source_path(settings, data.get('pdf_path'))
            if pdf is None or not pdf.is_file():
                issues.append(diagnostic('PDF_MISSING', record.relative, 'Original PDF is not available',
                                         'error' if complete or data.get('evidence_status') == 'pdf_verified' else 'warning'))
            if record.type == 'literature-fulltext':
                fingerprint = data.get('text_sha256')
                if fingerprint and fingerprint != hashlib.sha256(record.body.encode('utf-8')).hexdigest():
                    issues.append(diagnostic('FULLTEXT_DRIFT', record.relative, 'Archived text differs from its recorded digest'))
                original = _source_path(settings, data.get('source_path'))
                if original and original.is_file() and data.get('source_sha256'):
                    raw = original.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != data['source_sha256']:
                        issues.append(diagnostic('SOURCE_DRIFT', record.relative, 'Original extraction input has changed'))
                    elif data.get('extraction_method') in ('text', 'cache', 'structured'):
                        try:
                            same = raw.decode('utf-8-sig') == record.body
                        except UnicodeDecodeError:
                            same = False
                        if not same:
                            issues.append(diagnostic('FULLTEXT_DRIFT', record.relative, 'Archived text no longer matches original input'))
        if str(record.type).startswith(('knowledge-', 'research-')) and record.type not in ('research-card', 'research-project'):
            rows = data.get('source_notes', [])
            if not isinstance(rows, list):
                issues.append(diagnostic('SOURCE_LIST', record.relative, 'source_notes must be a list'))
                rows = []
            note_sources = [reference(settings, value, records) for value in rows]
            if any(row is None or row.type != 'literature-note' for row in note_sources):
                issues.append(diagnostic('SOURCE_NOTE_MISSING', record.relative, 'Every source Note must resolve'))
            keys = {row.data.get('zotero_key') for row in note_sources if row and row.type == 'literature-note' and isinstance(row.data.get('zotero_key'), str)}
            declared = data.get('source_papers', [])
            if not isinstance(declared, list) or any(not isinstance(k, str) for k in declared) or set(declared) != keys:
                issues.append(diagnostic('SOURCE_PAPERS', record.relative, 'source_papers must equal the distinct referenced parent keys'))
            if data.get('evidence_status') not in (None, 'unverified', 'speculative') and not keys:
                issues.append(diagnostic('SOURCE_REQUIRED', record.relative, 'Supported synthesis needs actual source Notes'))
            if 'evidence_count' in data and data['evidence_count'] != len(keys):
                issues.append(diagnostic('EVIDENCE_COUNT', record.relative, 'Count distinct parent papers, not links'))
        issues.extend(_links(settings, record, records))
    for path, claim in claims:
        if claim.get('schema_version') != 2:
            issues.append(diagnostic('SCHEMA_VERSION', path, 'Expected claim sidecar schema 2'))
        page = reference(settings, claim.get('page_path'), records)
        if page is None or not isinstance(page.data.get('claim_ids'), list) or claim.get('claim_id') not in page.data['claim_ids']:
            issues.append(diagnostic('CLAIM_OWNER', path, 'Claim must be listed on one real owning page'))
        elif not isinstance(claim.get('text'), str) or not claim['text'].strip() or _words(claim['text']) not in _words(page.body):
            issues.append(diagnostic('CLAIM_DRIFT', path, 'Exact claim statement is absent from the owning page'))
        if not isinstance(claim.get('evidence_status'), str) or claim['evidence_status'] not in EVIDENCE:
            issues.append(diagnostic('EVIDENCE_STATE', path, 'Claim evidence status is unknown'))
        issues.extend(verify_claim(settings, claim, records))
    from . import process, review, provenance
    for module in (process, review, provenance):
        issues.extend(module.check(settings, records))
    errors = sum(item['level'] == 'error' for item in issues)
    return _readonly_report(settings, {'valid': errors == 0, 'errors': errors, 'warnings': sum(item['level'] == 'warning' for item in issues),
                                     'records': len(records), 'diagnostics': issues})
