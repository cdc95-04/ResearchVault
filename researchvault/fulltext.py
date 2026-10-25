"""Original text storage and bounded local recall, without analysis generation."""
from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
import re

from .config import contained
from .documents import scan, write_new, create_file
from .identity import check_records
from .safety import require_writable
from .validation import reference


def initialize(settings, apply=False):
    if apply:
        require_writable(settings, 'Vault initialization')
    folders = []
    for role in settings.options['paths']:
        folders.append(settings.folder(role))
        folders.extend(contained(settings.folder(role), child) for child in settings.options['folders'].get(role, []))
    source = settings.repository / 'templates'
    if not source.is_dir():
        raise ValueError('Canonical templates are unavailable; run from the source checkout')
    copies = []
    for path in sorted(source.iterdir()):
        if path.is_file():
            target = contained(settings.folder('templates'), path.name)
            if not target.exists():
                copies.append((path, target))
    missing = [path for path in folders if not path.exists()]
    if apply:
        for path in missing:
            path.mkdir(parents=True, exist_ok=True)
        for source_path, target in copies:
            create_file(target, source_path.read_bytes())
    return {'applied': apply, 'folders': [settings.relative(p) for p in missing],
            'templates': [settings.relative(p) for _, p in copies]}


def original_file(settings, value):
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError('Original source file is unavailable')
    if not settings.options['synthetic'] and (path.is_relative_to(settings.repository) or path.is_relative_to(settings.vault)):
        raise ValueError('Real original sources must stay outside repository and Vault')
    return path


def archive(settings, record, source_path, *, method='text', note_path=None, apply=False):
    """Archive supplied original text or a PDF extraction, never a Paper Note."""
    if apply:
        require_writable(settings, 'Fulltext archive')
    if method not in {'text', 'cache', 'structured', 'pdf'}:
        raise ValueError('method must identify text, cache, structured, or pdf input')
    record = dict(record)
    check_records([record])
    if record.get('library_id') != settings.options['zotero']['library_id']:
        raise ValueError('Source is in another library')
    if not record.get('pdf_key'):
        raise ValueError('Archive requires a distinct source attachment key')
    source = original_file(settings, source_path)
    raw = source.read_bytes()
    if method == 'pdf':
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted or not reader.pages:
            raise ValueError('Source PDF is encrypted or has no pages')
        body = '\n\n'.join(page.extract_text() or '' for page in reader.pages)
        record['pdf_path'] = str(source)
    else:
        body = raw.decode('utf-8-sig')
    if not body.strip():
        raise ValueError('Extraction contains no text; record a partial state instead')
    if record.get('pdf_path'):
        record['pdf_path'] = str(original_file(settings, record['pdf_path']))
    existing = scan(settings) if settings.vault.exists() else []
    check_records([r.data for r in existing if r.type in ('literature-note', 'literature-fulltext')] + [record])
    if note_path:
        settings.resolve(note_path)
    target = contained(settings.folder('fulltext'), record['zotero_key'] + '.md')
    metadata = {k: record.get(k) for k in ('library_id', 'zotero_key', 'pdf_key', 'doi', 'arxiv_id', 'title', 'pdf_path')}
    metadata.update(schema_version=2, type='literature-fulltext', note_path=note_path,
                    source_path=str(source), source_sha256=hashlib.sha256(raw).hexdigest(),
                    text_sha256=hashlib.sha256(body.encode('utf-8')).hexdigest(), extraction_method=method)
    matches = [r for r in existing if r.type == 'literature-fulltext' and r.data.get('zotero_key') == record['zotero_key']]
    if matches:
        old = matches[0]
        if len(matches) != 1 or old.body != body or any(old.data.get(k) != metadata[k] for k in ('pdf_key', 'library_id', 'source_sha256', 'extraction_method')):
            raise ValueError('Existing Fulltext differs; inspect a diff, do not overwrite it')
        return {'applied': False, 'reused': True, 'path': old.relative, 'metadata': old.data}
    if target.exists():
        raise ValueError('Archive destination is occupied')
    if apply:
        write_new(target, metadata, body)
    return {'applied': apply, 'reused': False, 'path': settings.relative(target), 'metadata': metadata}


def retrieve(settings, query, *, supplementary=False):
    if not isinstance(query, str) or not query.strip():
        raise ValueError('A nonempty search query is required')
    records = scan(settings)
    tokens = query.casefold().split()
    def found(record):
        text = (str(record.data.get('title', '')) + '\n' + record.body).casefold()
        return all(token in text for token in tokens)
    primary = [r for r in records if r.type == 'literature-note' or str(r.type).startswith('knowledge-')]
    hits = [r for r in primary if found(r)]
    layers = ['literature-note', 'knowledge']
    if supplementary or not any(r.type == 'literature-note' for r in hits):
        layers.append('literature-fulltext')
        hits.extend(r for r in records if r.type == 'literature-fulltext' and found(r))
    parents, rows = set(), []
    for record in hits:
        keys = set()
        if record.type in ('literature-note', 'literature-fulltext'):
            keys.add((record.data.get('library_id'), record.data.get('zotero_key')))
        for path in record.data.get('source_notes', []) if isinstance(record.data.get('source_notes', []), list) else []:
            note = reference(settings, path, records)
            if note and note.type == 'literature-note':
                keys.add((note.data.get('library_id'), note.data.get('zotero_key')))
        parents.update((library, key) for library, key in keys if key)
        rows.append({'path': record.relative, 'type': record.type, 'title': record.data.get('title'),
                     'evidence_status': record.data.get('evidence_status', 'unverified')})
    return {'query': query, 'layers': layers, 'matches': rows, 'record_count': len(rows),
            'paper_count': len(parents), 'coverage': 'selected local Vault only; unseen literature is unknown'}


def ingest(settings, batch, *, apply=False):
    if apply:
        require_writable(settings, 'Batch ingestion')
    if not isinstance(batch, list) or not batch:
        raise ValueError('Ingest requires an explicit nonempty list of selected records')
    rows = []
    for index, item in enumerate(batch):
        try:
            if not isinstance(item, dict):
                raise ValueError('Batch entry must be an object')
            result = archive(settings, item['record'], item['source_path'], method=item.get('method', 'text'),
                             note_path=item.get('note_path'), apply=apply)
            rows.append({'index': index, 'status': 'reused' if result['reused'] else 'archived' if apply else 'planned', **result})
        except (KeyError, ValueError, OSError, TypeError) as exc:
            rows.append({'index': index, 'status': 'blocked', 'reason': str(exc)})
    return {'applied': apply, 'items': rows, 'blocked': sum(r['status'] == 'blocked' for r in rows)}


def diff(settings, path, proposed):
    original = settings.resolve(path)
    before = original.read_text(encoding='utf-8-sig')
    after = Path(proposed).read_text(encoding='utf-8-sig')
    return {'path': path, 'diff': ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                             fromfile=path, tofile='proposed/' + path)), 'applied': False}


def migration(settings):
    """Inventory incompatible records for manual migration; never move user files."""
    items = []
    from .documents import read_record, record_paths
    for path in record_paths(settings):
        try:
            record = read_record(path, settings.vault)
            reasons = []
            if record.data.get('schema_version') != 2:
                reasons.append('Review fields against schema 2 templates')
            if record.type in ('paper', 'fulltext', 'experiment'):
                reasons.append('Map legacy type to the explicit source or scientific object type')
            if record.type in ('paper', 'literature-note', 'fulltext', 'literature-fulltext') and not record.data.get('zotero_key'):
                reasons.append('Resolve parent identity from authoritative metadata before migration')
            if reasons:
                items.append({'path': record.relative, 'actions': reasons})
        except ValueError as exc:
            items.append({'path': settings.relative(path), 'actions': [str(exc)]})
    return {'applied': False, 'items': items, 'policy': 'manual reviewed migration; existing paths and content are preserved'}
