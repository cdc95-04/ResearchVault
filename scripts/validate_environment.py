"""Explicit local read-only inspection; private outputs stay in ignored scratch.

SQLite snapshot inspection is a declared validation method, never an application
adapter or a silent fallback from Zotero's Local API. Original files are opened
only for reading. No application is launched and no remote service is contacted.
The required --zotero-data argument selects this inspection's filesystem root;
core runtime configuration does not select a Zotero database.
"""
from pathlib import Path
import argparse
from collections import Counter
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from researchvault.documents import load_yaml
from researchvault.config import contained, native
from researchvault.safety import validation_output


def fingerprint(path):
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(stream.read()).hexdigest()
    return {'sha256': value, 'bytes': path.stat().st_size}


def inventory_files(root):
    files, skipped = {}, 0
    for directory, folders, names in os.walk(root, followlinks=False):
        base = Path(directory)
        safe = []
        for name in folders:
            child = base / name
            if child.resolve().is_relative_to(root) and not child.is_symlink() and not (getattr(child.stat(), 'st_file_attributes', 0) & 0x400):
                safe.append(name)
            else:
                skipped += 1
        folders[:] = safe
        for name in names:
            path = base / name
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                skipped += 1
                continue
            files[path.relative_to(root).as_posix()] = fingerprint(path)
    return files, skipped


def inspect(zotero_root, vault, workspace):
    zotero_root, vault, workspace = (native(value, Path.cwd()) for value in (zotero_root, vault, workspace))
    scratch = ROOT / '.qa'
    temp = Path(tempfile.gettempdir()).resolve()
    if not (workspace.is_relative_to(scratch) or workspace.is_relative_to(temp)):
        raise ValueError('Private validation workspace must be inside ignored .qa or OS temporary storage')
    protected = (zotero_root, vault)
    def output(name):
        return validation_output(workspace, name, protected_roots=protected)
    # Validate output isolation before reading either selected source.
    output('environment-summary.json')
    database = contained(zotero_root, 'zotero.sqlite')
    parts = [Path(str(database) + ending) for ending in ('', '-wal', '-shm') if Path(str(database) + ending).exists()]
    if not database.is_file():
        raise ValueError('Selected Zotero database is absent')
    before_db = {path.name: fingerprint(path) for path in parts}
    before_vault, skipped = inventory_files(vault)
    run = 'snapshot-' + uuid.uuid4().hex
    for path in parts:
        target = output(run + '/' + path.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with path.open('rb') as source, target.open('xb') as dest:
            while chunk := source.read(1024 * 1024):
                dest.write(chunk)
    def current_database():
        return {Path(str(database) + ending).name: fingerprint(contained(zotero_root, database.name + ending))
                for ending in ('', '-wal', '-shm') if Path(str(database) + ending).exists()}
    if before_db != current_database():
        raise ValueError('Source database changed while copying; stop and obtain a stable snapshot')
    snapshot = output(run + '/zotero.sqlite')
    connection = sqlite3.connect(snapshot.as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only = ON')
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    connection.set_authorizer(lambda action, *args: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        items = {row['itemID']: dict(row) for row in connection.execute('SELECT i.itemID,i.key,i.libraryID,t.typeName FROM items i JOIN itemTypes t ON t.itemTypeID=i.itemTypeID')}
        for item in items.values():
            item.update(fields={}, authors=[], attachments=[], collections=[])
        for row in connection.execute('SELECT d.itemID,f.fieldName,v.value FROM itemData d JOIN fields f ON f.fieldID=d.fieldID JOIN itemDataValues v ON v.valueID=d.valueID'):
            if row['itemID'] in items:
                items[row['itemID']]['fields'][row['fieldName']] = row['value']
        for row in connection.execute('SELECT ic.itemID,c.firstName,c.lastName FROM itemCreators ic JOIN creators c ON c.creatorID=ic.creatorID ORDER BY ic.orderIndex'):
            if row['itemID'] in items:
                items[row['itemID']]['authors'].append((row['firstName'] + ' ' + row['lastName']).strip())
        attachments = [dict(row) for row in connection.execute('SELECT itemID,parentItemID,linkMode,contentType,path FROM itemAttachments')]
        for row in attachments:
            if row['parentItemID'] in items:
                row['key'] = items[row['itemID']]['key']
                items[row['parentItemID']]['attachments'].append(row)
        for row in connection.execute('SELECT itemID,collectionID FROM collectionItems'):
            if row['itemID'] in items:
                items[row['itemID']]['collections'].append(row['collectionID'])
        deleted = {r[0] for r in connection.execute('SELECT itemID FROM deletedItems')} if 'deletedItems' in tables else set()
        parents = [item for item in items.values() if item['typeName'] not in ('attachment', 'note', 'annotation') and item['itemID'] not in deleted]
    finally:
        connection.close()
    doi_counts = Counter(i['fields'].get('DOI', '').strip().casefold() for i in parents if i['fields'].get('DOI'))
    title_counts = Counter(re.sub(r'\W+', '', i['fields'].get('title', '')).casefold() for i in parents if i['fields'].get('title'))
    zotero = {'parent_items': len(parents), 'pdf_attachments': sum(a['contentType'] == 'application/pdf' for i in parents for a in i['attachments']),
              'without_pdf': sum(not any(a['contentType'] == 'application/pdf' for a in i['attachments']) for i in parents),
              'multiple_attachments': sum(len(i['attachments']) > 1 for i in parents),
              'with_doi': sum(bool(i['fields'].get('DOI')) for i in parents),
              'arxiv_mentions': sum('arxiv' in json.dumps(i['fields']).casefold() for i in parents),
              'with_venue': sum(bool(i['fields'].get('publicationTitle') or i['fields'].get('conferenceName') or i['fields'].get('proceedingsTitle')) for i in parents),
              'with_collections': sum(bool(i['collections']) for i in parents),
              'unicode_title_or_author': sum(any(ord(c) > 127 for c in i['fields'].get('title', '') + ''.join(i['authors'])) for i in parents),
              'missing_title_or_authors': sum(not i['fields'].get('title') or not i['authors'] for i in parents),
              'duplicate_doi_groups': sum(n > 1 for n in doi_counts.values()),
              'normalized_title_duplicate_groups': sum(n > 1 for n in title_counts.values())}
    obsidian = Counter(files=len(before_vault), skipped_links=skipped)
    for relative in before_vault:
        if not relative.lower().endswith('.md') or relative.startswith('.obsidian/'):
            continue
        path = vault / relative
        text = path.read_text(encoding='utf-8-sig')
        obsidian['markdown'] += 1
        obsidian['nested_markdown'] += '/' in relative
        obsidian['wiki_links'] += bool(re.search(r'\[\[[^\]]+\]\]', text))
        obsidian['markdown_links'] += bool(re.search(r'\[[^\]]*\]\([^)]+\)', text))
        obsidian['canonical_key_filename'] += bool(re.fullmatch(r'[A-Z0-9]{8}', path.stem))
        front = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', text, re.S)
        if front:
            obsidian['frontmatter'] += 1
            try:
                data = load_yaml(front.group(1))
                obsidian['schema2_records'] += isinstance(data, dict) and data.get('schema_version') == 2
            except ValueError:
                obsidian['invalid_frontmatter'] += 1
    after_db = current_database()
    after_vault, after_skipped = inventory_files(vault)
    unchanged = before_db == after_db and before_vault == after_vault and skipped == after_skipped
    report = {'method': 'explicit isolated SQLite snapshot plus direct read-only Markdown inspection', 'zotero': zotero,
              'obsidian': dict(obsidian), 'source_files_unchanged': unchanged, 'source_writes_performed': False,
              'live_local_api_validated': False, 'private_data_in_public_report': False}
    private = {'zotero_root': str(zotero_root), 'vault_root': str(vault), 'parents': parents,
               'database_before': before_db, 'vault_before': before_vault}
    for name, data in (('inventory.private.json', private), ('environment-summary.json', report)):
        target = output(run + '/' + name)
        with target.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
    if not unchanged:
        raise ValueError('Source files changed during inspection; do not claim a stable read-only observation')
    return report, run


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zotero-data', required=True, help='Explicit Zotero filesystem root for read-only snapshot inspection')
    parser.add_argument('--vault', required=True, help='Explicit Vault root for read-only Markdown inspection')
    parser.add_argument('--workspace', required=True, help='Isolated private output directory, separate from both source roots')
    args = parser.parse_args()
    try:
        report, run = inspect(args.zotero_data, args.vault, args.workspace)
        print(json.dumps({'report': report, 'scratch_run': run}, indent=2))
    except (ValueError, OSError, sqlite3.Error) as error:
        print(json.dumps({'status': 'blocked', 'error_type': type(error).__name__, 'details_withheld': True}))
        raise SystemExit(2)
