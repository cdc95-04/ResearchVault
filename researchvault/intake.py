"""Explicit selected-identifier intake; reuse the existing evidence/write contracts.

Preview is offline and has no filesystem effects. Apply serializes workflows in
the configured runtime, freezes metadata, keeps durable API receipts, and only
publishes new Vault records. Scientific analysis is an optional source-bound
capture, never inferred from a title or from a successful download.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
from http.client import HTTPException
import io
import json
import os
from pathlib import Path
import time
import uuid

import yaml

from . import acquisition, discovery, fulltext, notes, resolution
from .config import contained
from .documents import scan
from .safety import require_writable
from .zotero import Client, MANUAL, publication_match


class Blocked(ValueError):
    """Safe, fixed status codes; exception text from remote services is not logged."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _json(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise Blocked('RUNTIME_STATE_CONFLICT')
    return value


def _store(path, value):
    """Replace only our mutable runtime state, never a research record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.next')
    if path.is_symlink() or pending.exists() or pending.is_symlink():
        raise Blocked('RUNTIME_STATE_CONFLICT')
    with pending.open('xb') as stream:
        stream.write(_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


def _immutable(path, content):
    """Fsync first, then publish with a create-only hard link on the same volume."""
    path = Path(path)
    if path.is_symlink():
        raise Blocked('FILE_CONFLICT')
    if path.exists():
        if not path.is_file() or path.read_bytes() != content:
            raise Blocked('FILE_CONFLICT')
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.staging')
    if pending.is_symlink():
        raise Blocked('FILE_CONFLICT')
    if pending.exists():
        if pending.read_bytes() != content:
            raise Blocked('FILE_CONFLICT')
    else:
        with pending.open('xb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    # os.rename overwrites on POSIX. Hard links give create-if-absent semantics
    # on both supported platforms; an unsupported filesystem fails closed.
    try:
        os.link(pending, path)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != content:
            raise Blocked('FILE_CONFLICT') from None
        return False
    finally:
        if path.exists() and not path.is_symlink() and path.read_bytes() == content:
            pending.unlink(missing_ok=True)
    return True


@contextmanager
def _lock(root):
    root.mkdir(parents=True, exist_ok=True)
    path = contained(root, 'workflow.lock')
    owner = uuid.uuid4().hex.encode('ascii')
    try:
        with path.open('xb') as stream:
            stream.write(owner)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise Blocked('INTAKE_LOCKED_RECONCILE_BEFORE_RETRY') from None
    try:
        yield
    finally:
        if path.is_file() and not path.is_symlink() and path.read_bytes() == owner:
            path.unlink()


def _event(directory, event, **fields):
    path = contained(directory, 'events.jsonl')
    if path.is_symlink():
        raise Blocked('RUNTIME_STATE_CONFLICT')
    with path.open('ab') as stream:
        stream.write(_bytes({'at': discovery.now(), 'event': event, **fields}) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def _brief(candidate):
    return {key: candidate.get(key) for key in
            ('canonical_id', 'title', 'authors', 'year', 'doi', 'arxiv_id_version',
             'version', 'venue', 'canonical_url', 'sources')}


def _metadata(raw, resolver, transport):
    try:
        candidate = resolver(raw, transport=transport)
    except (OSError, HTTPException):
        raise Blocked('METADATA_NETWORK_UNAVAILABLE') from None
    except ValueError:
        raise Blocked('IDENTITY_UNRESOLVED') from None
    return _check_metadata(candidate, resolution.parse(raw))


def _check_metadata(candidate, requested):
    if (not isinstance(candidate, dict) or candidate.get('identity_status') != 'VERIFIED_METADATA'
            or not candidate.get('canonical_id') or not candidate.get('title')
            or not candidate.get('authors') or type(candidate.get('year')) is not int
            or not candidate.get('sources')):
        raise Blocked('IDENTITY_UNRESOLVED')
    if requested['kind'] == 'doi' and candidate.get('doi') != requested['doi']:
        raise Blocked('IDENTITY_UNRESOLVED')
    if requested['kind'] == 'arxiv' and (candidate.get('arxiv_id') != requested['arxiv_id']
            or not candidate.get('arxiv_id_version')
            or requested.get('arxiv_id_version') and candidate['arxiv_id_version'] != requested['arxiv_id_version']):
        raise Blocked('IDENTITY_UNRESOLVED')
    if requested['kind'] == 'publisher' and candidate.get('canonical_url') != requested['canonical_url']:
        raise Blocked('IDENTITY_UNRESOLVED')
    return candidate


def _frozen(path):
    packet = _json(path)
    if not isinstance(packet, dict) or _sha(_bytes(packet.get('candidate'))) != packet.get('sha256'):
        raise Blocked('FROZEN_METADATA_CHANGED')
    return packet['candidate']


def _inventory(client, namespace):
    try:
        inventory = client.inventory()
    except (OSError, ValueError, HTTPException):
        raise Blocked('ZOTERO_LOCAL_API_UNAVAILABLE') from None
    if inventory.get('library') != namespace or not inventory.get('server_id'):
        raise Blocked('ZOTERO_IDENTITY_UNAVAILABLE')
    return inventory


def _parents(candidate, inventory):
    exact, uncertain = [], []
    for item in inventory['items']:
        data = item.get('data', item)
        if data.get('itemType') in {'attachment', 'note', 'annotation'} or data.get('deleted'):
            continue
        try:
            match = publication_match(candidate, item)
        except ValueError:
            raise Blocked('WRITE_CONFLICT') from None
        if match == 'EXACT':
            exact.append(item)
        elif match == 'AMBIGUOUS':
            uncertain.append(item)
    if uncertain or len(exact) > 1:
        raise Blocked('WRITE_CONFLICT')
    return exact[0] if exact else None


def _attachments(parent, inventory):
    if not parent:
        return []
    return [item for item in inventory['items']
            if item.get('data', item).get('parentItem') == parent['key']
            and item.get('data', item).get('itemType') == 'attachment'
            and item.get('data', item).get('contentType') == 'application/pdf'
            and not item.get('data', item).get('deleted')]


def _receipt(directory, name, inventory, *, parent_key=None, pdf_sha256=None):
    """Completed receipts are reconciled, uncertain receipts are never retried."""
    path = contained(directory, name + '.jsonl')
    if not path.exists():
        return path, None
    try:
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        first, last = rows[0], rows[-1]
        if (first.get('status') != 'INTENT' or last.get('status') != 'COMPLETE'
                or first.get('library') != inventory['library']
                or first.get('server_id') != inventory['server_id']):
            raise ValueError()
        key = last.get('key') if name == 'parent' else last.get('pdf_key')
        found = [item for item in inventory['items'] if item['key'] == key]
        if len(found) != 1:
            raise ValueError()
        if name != 'parent' and (last.get('zotero_key') != parent_key
                                or last.get('sha256') != pdf_sha256
                                or found[0]['data'].get('parentItem') != parent_key):
            raise ValueError()
        return path, found[0]
    except (KeyError, ValueError, IndexError, OSError):
        raise Blocked(MANUAL) from None


def _alias_receipts(settings, candidate, directory, inventory, parent, namespace):
    """Another spelling of an identity must not bypass an uncertain write."""
    root = contained(settings.runtime, 'intake/workflows')
    for saved_path in root.glob('*/state.json'):
        safe = contained(root, saved_path.relative_to(root).as_posix())
        if safe.parent == directory:
            continue
        saved = _json(safe)
        if saved.get('library') != namespace:
            continue
        if saved.get('canonical_id') != candidate['canonical_id']:
            continue
        frozen = _frozen(contained(safe.parent, 'candidate.json'))
        if _sha(_bytes(frozen)) != saved.get('candidate_sha256'):
            raise Blocked('FROZEN_METADATA_CHANGED')
        receipts = [contained(safe.parent, name + '.jsonl') for name in ('parent', 'attachment')]
        if not any(path.exists() for path in receipts):
            continue
        if not inventory or saved.get('server_id') != inventory['server_id']:
            raise Blocked(MANUAL)
        _, old_parent = _receipt(safe.parent, 'parent', inventory)
        if old_parent and (not parent or parent['key'] != old_parent['key']):
            raise Blocked(MANUAL)
        _receipt(safe.parent, 'attachment', inventory, parent_key=parent['key'] if parent else None,
                 pdf_sha256=saved.get('pdf', {}).get('sha256'))


def _verify(content, candidate, verifier):
    bound = copy.deepcopy(candidate)
    if 'source_evidence' in bound:
        bound['source_evidence']['sha256'] = _sha(content)
    result = verifier(content, bound)
    if result.get('status') not in acquisition.PDF_STATES:
        raise Blocked('INVALID_PDF_VERDICT')
    return bound, result


def _download(settings, candidate, directory, *, enabled, email, transport, verifier, pause):
    if not enabled:
        raise Blocked('ACQUISITION_DISABLED')
    routes = list(candidate.get('lawful_routes', []))
    if not routes:
        if not candidate.get('doi'):
            raise Blocked('PDF_UNAVAILABLE')
        if not email:
            raise Blocked('OA_CONTACT_REQUIRED')
        routes = [{'url': row['url_for_pdf'], 'version': row['version'],
                   'method': 'unpaywall', 'license': row['license'],
                   'source_url': row.get('url_for_landing_page'), 'host_type': row['host_type']}
                  for row in acquisition.oa_locations(candidate['doi'], email, transport=transport)]
    if not routes:
        raise Blocked('PDF_UNAVAILABLE')
    last = 'PDF_UNAVAILABLE'
    for route in routes:
        try:
            pause(settings.options['acquisition']['interval'])
            response, final_url = discovery.get(route['url'], transport=transport,
                                                max_bytes=settings.options['acquisition']['max_bytes'])
            if response.status != 200 or response.header('Content-Type', '').split(';')[0].strip() != 'application/pdf':
                raise Blocked('PDF_HTTP_OR_MEDIA_TYPE')
            selected = copy.deepcopy(candidate)
            if not selected.get('expected_version'):
                selected['expected_version'] = route.get('version')
            if 'source_evidence' in selected:
                selected['source_evidence']['acquisition_url'] = final_url
            selected, verdict = _verify(response.body, selected, verifier)
            if verdict['status'] == 'VERIFIED' and (not selected.get('expected_version')
                    or not route.get('version') or verdict.get('observed_version') != route['version']
                    or selected['expected_version'] != route['version']):
                verdict = {**verdict, 'status': 'PROBABLE', 'reason': 'Selected, route and observed versions must agree'}
            _event(directory, 'pdf_identity', status=verdict['status'], source_url=final_url,
                   sha256=_sha(response.body), method=route['method'], version=route.get('version'))
            if verdict['status'] != 'VERIFIED':
                last = 'PDF_' + verdict['status']
                continue
            digest = _sha(response.body)
            path = contained(settings.runtime, 'intake/artifacts/' + digest + '.pdf')
            created = _immutable(path, response.body)
            return {'path': str(path), 'sha256': digest, 'source_url': final_url,
                    'method': route['method'], 'license': route.get('license'),
                    'version': route.get('version'), 'verdict': verdict,
                    'candidate': selected, 'reused': not created}
        except (OSError, ValueError, KeyError, HTTPException) as exc:
            last = exc.code if isinstance(exc, Blocked) else 'PDF_ROUTE_FAILED'
            _event(directory, 'route_failed', status=last, exception_type=type(exc).__name__)
    raise Blocked(last)


def _item(candidate):
    arxiv = candidate.get('arxiv_id_version')
    data = {'itemType': 'preprint' if arxiv and not candidate.get('doi') else 'journalArticle',
            'title': candidate['title'], 'date': str(candidate['year']),
            # Preserve unstructured source names using Zotero's single-field
            # form. Do not guess a surname or rely on omitted firstName defaults.
            'creators': [{'creatorType': 'author', 'name': author} for author in candidate['authors']],
            'url': candidate['canonical_url']}
    if candidate.get('doi'):
        data['DOI'] = candidate['doi']
    if arxiv:
        data['extra'] = 'arXiv: ' + arxiv
    if candidate.get('venue') and data['itemType'] == 'journalArticle':
        data['publicationTitle'] = candidate['venue']
    return data


def _payload(data, body):
    return ('---\n' + yaml.safe_dump(data, sort_keys=False, allow_unicode=True) + '---\n' + body).encode('utf-8')


def _archive(settings, candidate, parent, pdf, directory, state, analysis, crash):
    """Stage the pair and its hashes before either create-only publication."""
    record = {'library_id': settings.options['zotero']['library_id'], 'zotero_key': parent['key'],
              'pdf_key': pdf['pdf_key'], 'title': candidate['title'], 'doi': candidate.get('doi'),
              'arxiv_id': candidate.get('arxiv_id_version')}
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(pdf['content']), strict=True)
        if reader.is_encrypted or not reader.pages:
            raise Blocked('EXTRACTION_UNAVAILABLE')
        pages = [page.extract_text() or '' for page in reader.pages]
    except Exception:
        raise Blocked('EXTRACTION_UNAVAILABLE') from None
    if not any(page.strip() for page in pages):
        raise Blocked('EXTRACTION_UNAVAILABLE')
    note_path = settings.relative(contained(settings.folder('papers'), 'Other/' + parent['key'] + '.md'))
    fulltext_path = settings.relative(contained(settings.folder('fulltext'), parent['key'] + '.md'))
    # Existing user records can be reused only after an exact reciprocal check.
    records = scan(settings) if settings.vault.exists() else []
    related = [r for r in records if r.type in {'literature-note', 'literature-fulltext'}
               and r.data.get('library_id') == record['library_id']
               and r.data.get('zotero_key') == record['zotero_key']]
    publication = state.get('publication')
    if related and not publication:
        by_type = {kind: [r for r in related if r.type == kind] for kind in ('literature-note', 'literature-fulltext')}
        if any(len(group) != 1 for group in by_type.values()):
            raise Blocked('VAULT_RECORD_CONFLICT')
        note, text = by_type['literature-note'][0], by_type['literature-fulltext'][0]
        text_digest = _sha('\n\n'.join(pages).encode('utf-8'))
        if (note.data.get('fulltext_path') != text.relative or text.data.get('note_path') != note.relative
                or any(r.data.get('pdf_key') != record['pdf_key'] for r in related)
                or text.data.get('source_sha256') != pdf['sha256']
                or note.data.get('pdf_sha256') != pdf['sha256']
                or any(r.data.get('text_sha256') != text_digest for r in related)
                or text.data.get('source_path') != pdf['path'] or text.data.get('extraction_method') != 'pdf'
                or text.body != '\n\n'.join(pages)
                or any(r.data.get('pdf_path') != pdf['path'] for r in related)
                or any(r.data.get('doi') != record['doi'] or r.data.get('arxiv_id') != record['arxiv_id']
                       or r.data.get('title') != record['title'] for r in related)):
            raise Blocked('VAULT_RECORD_CONFLICT')
        if analysis is not None:
            raise Blocked('ANALYSIS_CHANGE_REQUIRES_REVIEWED_DIFF')
        return {'note_path': note.relative, 'fulltext_path': text.relative,
                'analysis_status': note.data.get('analysis_status', 'EXISTING_RECORD_UNASSESSED'), 'reused': True}
    if publication:
        # Never regenerate a previously staged Note, especially after a user edit.
        staged = contained(settings.vault, publication['staging'])
        expected = [('fulltext.txt', fulltext_path), ('note.txt', note_path)]
        if ([(item['name'], item['path']) for item in publication['files']] != expected
                or publication['staging'] != settings.relative(contained(settings.folder('metadata'), 'imports/intake/' + directory.name))
                or any(r.relative not in {note_path, fulltext_path} for r in related)):
            raise Blocked('VAULT_RECORD_CONFLICT')
        if publication.get('pdf_sha256') != pdf['sha256'] or publication.get('pdf_key') != record['pdf_key']:
            raise Blocked('VAULT_RECORD_CONFLICT')
        if analysis is not None and publication.get('analysis_sha256') != _sha(_bytes(analysis)):
            raise Blocked('ANALYSIS_CHANGE_REQUIRES_REVIEWED_DIFF')
        for item in publication['files']:
            content = contained(staged, item['name']).read_bytes()
            if _sha(content) != item['sha256']:
                raise Blocked('VAULT_RECORD_CONFLICT')
            target = settings.resolve(item['path'])
            if target.exists() and (target.is_symlink() or target.read_bytes() != content):
                raise Blocked('VAULT_RECORD_CONFLICT')
    else:
        if settings.resolve(note_path).exists() or settings.resolve(fulltext_path).exists():
            raise Blocked('VAULT_RECORD_CONFLICT')
        planned = fulltext.archive(settings, record, pdf['path'], method='pdf', note_path=note_path)
        if (planned['metadata'].get('source_sha256') != pdf['sha256']
                or planned['metadata'].get('text_sha256') != _sha('\n\n'.join(pages).encode('utf-8'))
                or planned['metadata'].get('pdf_path') != pdf['path']
                or planned['metadata'].get('source_path') != pdf['path']):
            raise Blocked('SOURCE_CHANGED_DURING_ARCHIVE')
        rendered = notes.render(record, note_path=note_path, fulltext_path=fulltext_path,
                                pdf_path=pdf['path'], pdf_sha256=pdf['sha256'], pages=pages,
                                metadata_sources=candidate['sources'], analysis=analysis,
                                synthetic=settings.options['synthetic'])
        files = [('fulltext', fulltext_path, _payload(planned['metadata'], '\n\n'.join(pages))),
                 ('note', note_path, _payload(rendered['data'], rendered['body']))]
        staging = contained(settings.folder('metadata'), 'imports/intake/' + directory.name)
        publication = {'staging': settings.relative(staging), 'pdf_sha256': pdf['sha256'],
                       'pdf_key': record['pdf_key'], 'files': [],
                       'analysis_sha256': _sha(_bytes(analysis)) if analysis is not None else None,
                       'analysis_status': rendered['analysis_status']}
        for name, path, content in files:
            _immutable(contained(staging, name + '.txt'), content)
            publication['files'].append({'name': name + '.txt', 'path': path, 'sha256': _sha(content)})
        rendered['handoff']['note_sha256'] = _sha(files[1][2])
        _immutable(contained(staging, 'analysis-handoff.json'), _bytes(rendered['handoff']))
        state['publication'] = publication
        _store(contained(directory, 'state.json'), state)
        _event(directory, 'vault_pair_staged', files=[{'path': i['path'], 'sha256': i['sha256']} for i in publication['files']])
    staged = settings.resolve(publication['staging'])
    for index, item in enumerate(publication['files']):
        content = contained(staged, item['name']).read_bytes()
        created = _immutable(settings.resolve(item['path']), content)
        _event(directory, 'vault_record_published', path=item['path'], sha256=item['sha256'], reused=not created)
        if crash:
            crash('after_fulltext' if index == 0 else 'after_note')
    return {'note_path': publication['files'][1]['path'], 'fulltext_path': publication['files'][0]['path'],
            'analysis_status': publication['analysis_status'], 'reused': False}


def _process(settings, raw, identity, namespace, directory, *, resume, enabled, allow_create,
             email, transport, client, resolver, verifier, analysis, pause, crash, progress):
    path = contained(directory, 'state.json')
    candidate_path = contained(directory, 'candidate.json')
    directory.mkdir(parents=True, exist_ok=True)
    state = _json(path) if path.exists() else {'schema_version': 1, 'request_id': identity['canonical_id'],
                                             'library': namespace, 'status': 'RESOLVING'}
    if state.get('request_id') != identity['canonical_id'] or state.get('library') != namespace:
        raise Blocked('RESUME_CONFLICT')
    if (path.exists() or candidate_path.exists()) and not resume:
        raise Blocked('RESUME_REQUIRED')
    if candidate_path.exists():
        candidate = _check_metadata(_frozen(candidate_path), identity)
        if state.get('candidate_sha256') and _sha(_bytes(candidate)) != state['candidate_sha256']:
            raise Blocked('FROZEN_METADATA_CHANGED')
        state['candidate_sha256'] = _sha(_bytes(candidate))
        state['canonical_id'] = candidate['canonical_id']
        if state['status'] == 'RESOLVING':
            state['status'] = 'METADATA_RESOLVED'
        _store(path, state)
    elif 'candidate_sha256' in state:
        raise Blocked('FROZEN_METADATA_CHANGED')
    else:
        if identity['kind'] == 'arxiv':
            pause(max(3.0, settings.options['acquisition']['interval']))
        candidate = _metadata(raw, resolver, transport)
        _immutable(candidate_path, _bytes({'candidate': candidate, 'sha256': _sha(_bytes(candidate))}))
        if crash:
            crash('after_metadata_capture')
        state['candidate_sha256'] = _sha(_bytes(candidate))
        state['canonical_id'] = candidate['canonical_id']
        state['status'] = 'METADATA_RESOLVED'
        _store(path, state)
        _event(directory, 'metadata_frozen', canonical_id=candidate['canonical_id'], sha256=state['candidate_sha256'])
    result = progress
    result.update(identity=_brief(candidate), parent_created=0, attachment_created=0,
                  pdf_acquired=0, pdf_reused=0, zotero_read_back_verified=False)
    # Acquisition is useful even when the desktop or its write credential is absent.
    # Inventory is always attempted before any create, and before preferring a PDF.
    inventory, unavailable = None, None
    try:
        inventory = _inventory(client, namespace)
    except Blocked as exc:
        unavailable = exc.code
    parent = _parents(candidate, inventory) if inventory else None
    if parent:
        result['parent_key'] = parent['key']
    _alias_receipts(settings, candidate, directory, inventory, parent, namespace)
    attachments = _attachments(parent, inventory) if inventory else []
    if len(attachments) > 1:
        raise Blocked('WRITE_CONFLICT')
    if inventory:
        if state.get('server_id') and state['server_id'] != inventory['server_id']:
            raise Blocked(MANUAL)
        state['server_id'] = inventory['server_id']
        _store(path, state)
        # Even if inventory happens to contain the item, an incomplete mutation
        # receipt requires manual reconciliation, not a new auto-attach attempt.
        _, saved_parent = _receipt(directory, 'parent', inventory)
        if saved_parent and (not parent or saved_parent['key'] != parent['key']):
            raise Blocked(MANUAL)
        if contained(directory, 'attachment.jsonl').exists():
            _receipt(directory, 'attachment', inventory, parent_key=parent['key'] if parent else None,
                     pdf_sha256=state.get('pdf', {}).get('sha256'))
    pdf = None
    if attachments:
        try:
            pdf = client.read_pdf(attachments[0]['key'], parent_key=parent['key'],
                                  max_bytes=settings.options['acquisition']['max_bytes'])
            bound, verdict = _verify(pdf['content'], candidate, verifier)
        except (ValueError, OSError):
            raise Blocked('EXISTING_ATTACHMENT_REVIEW_REQUIRED') from None
        if verdict['status'] != 'VERIFIED':
            raise Blocked('EXISTING_ATTACHMENT_' + verdict['status'])
        result['pdf_reused'] = 1
        result['pdf'] = {'sha256': pdf['sha256'], 'method': 'existing_zotero_attachment', 'status': verdict['status']}
    else:
        acquired = state.get('pdf')
        if acquired:
            cache = contained(settings.runtime, 'intake/artifacts/' + acquired['sha256'] + '.pdf')
            content = cache.read_bytes()
            if _sha(content) != acquired['sha256']:
                raise Blocked('CACHED_PDF_CHANGED')
            bound, verdict = _verify(content, acquired['candidate'], verifier)
            if verdict['status'] != 'VERIFIED':
                raise Blocked('CACHED_PDF_REVIEW_REQUIRED')
            acquired['path'] = str(cache)
            result['pdf_reused'] = 1
        else:
            acquired = _download(settings, candidate, directory, enabled=enabled, email=email,
                                 transport=transport, verifier=verifier, pause=pause)
            state['pdf'] = acquired
            state['status'] = 'PDF_VERIFIED'
            _store(path, state)
            result['pdf_acquired'] = 1
            result['pdf_reused'] = int(acquired['reused'])
            bound = acquired['candidate']
        result['pdf'] = {key: acquired[key] for key in ('path', 'sha256', 'source_url', 'method', 'version')}
        if unavailable:
            return {**result, 'status': unavailable, 'write_status': 'WRITE_BLOCKED'}
        if not allow_create:
            return {**result, 'status': 'ZOTERO_WRITE_AUTHORIZATION_REQUIRED', 'write_status': 'WRITE_BLOCKED'}
        if not os.environ.get(settings.options['zotero']['api_key_env']):
            return {**result, 'status': 'ZOTERO_WRITE_CREDENTIAL_REQUIRED', 'write_status': 'WRITE_BLOCKED'}
        if not parent:
            receipt, _ = _receipt(directory, 'parent', inventory)
            created = client.create_item(_item(candidate), apply=True, receipt_path=receipt)
            if created['status'] != 'CREATED':
                raise Blocked(MANUAL if created['status'] == MANUAL else 'WRITE_CONFLICT')
            parent = created['item']
            result['parent_created'] = 1
            result['parent_key'] = parent['key']
            state['parent_key'] = parent['key']
            state['status'] = 'PARENT_READ_BACK_VERIFIED'
            _store(path, state)
        # create_item and import_pdf both perform their own fresh dedup read.
        receipt = contained(directory, 'attachment.jsonl')
        imported = client.import_pdf(parent['key'], acquired['path'], bound, apply=True,
                                     receipt_path=receipt, verifier=verifier)
        if imported['status'] != 'CREATED':
            raise Blocked(MANUAL if imported['status'] == MANUAL else 'WRITE_CONFLICT')
        result['attachment_created'] = 1
        result['attachment_key'] = imported['pdf_key']
        pdf = client.read_pdf(imported['pdf_key'], parent_key=parent['key'],
                              max_bytes=settings.options['acquisition']['max_bytes'])
        if pdf['sha256'] != acquired['sha256']:
            raise Blocked('ZOTERO_ATTACHMENT_HASH_MISMATCH')
    latest = _inventory(client, namespace)
    readback = _parents(candidate, latest)
    final_attachments = _attachments(readback, latest)
    if (not readback or readback['key'] != parent['key'] or len(final_attachments) != 1
            or pdf['pdf_key'] != final_attachments[0]['key']):
        raise Blocked('ZOTERO_READ_BACK_FAILED')
    result.update(parent_key=parent['key'], attachment_key=pdf['pdf_key'], zotero_read_back_verified=True)
    state.update(parent_key=parent['key'], pdf_key=pdf['pdf_key'], status='ZOTERO_IMPORT_VERIFIED')
    _store(path, state)
    _event(directory, 'zotero_read_back_verified', parent_key=parent['key'], pdf_key=pdf['pdf_key'], sha256=pdf['sha256'])
    packet = analysis.get(candidate['canonical_id']) if analysis else None
    result.update(_archive(settings, candidate, parent, pdf, directory, state, packet, crash))
    result['status'] = 'ARCHIVED' if result['analysis_status'] == 'AGENT_ANALYSIS_CAPTURED' else 'ARCHIVED_ANALYSIS_PENDING'
    state['status'] = result['status']
    _store(path, state)
    return result


def run(settings, inputs, *, apply=False, resolve_metadata=False, enabled=False,
        allow_zotero_create=False, email=None, resume=False, analysis=None,
        transport=None, client=None, resolver=None, verifier=None, pause=None, crash=None):
    """Process a bounded batch. Injected transports enable offline end-to-end tests."""
    if not isinstance(inputs, list) or not inputs or any(not isinstance(raw, str) for raw in inputs):
        raise ValueError('intake requires an explicit nonempty identifier list')
    if analysis is not None and not isinstance(analysis, dict):
        raise ValueError('analysis must map canonical IDs to source-bound analysis packets')
    if apply:
        require_writable(settings, 'Identifier intake')
        if settings.runtime is None:
            raise ValueError('Identifier intake requires an explicit runtime outside the Vault')
    namespace = 'users/0' if settings.options['zotero']['library_id'] is None else 'groups/' + str(settings.options['zotero']['library_id'])
    client = client or Client(namespace, api_key_env=settings.options['zotero']['api_key_env'], read_only=settings.read_only)
    if client.library != namespace:
        raise ValueError('Client belongs to another library')
    resolver, verifier, pause = resolver or resolution.resolve, verifier or acquisition.verify_pdf, pause or time.sleep
    rows, seen = [], set()

    def execute():
        for index, raw in enumerate(inputs):
            directory = None
            progress = {}
            try:
                identity = resolution.parse(raw)
                request_id = identity['canonical_id']
                if request_id in seen:
                    rows.append({'index': index, 'request_id': request_id, 'status': 'DUPLICATE_INPUT'})
                    continue
                seen.add(request_id)
                row = {'index': index, 'request_id': request_id}
                if not apply:
                    row.update(status='PLANNED', identity=identity, network_reads=False, mutations=False)
                    if resolve_metadata:
                        if identity['kind'] == 'arxiv':
                            pause(max(3.0, settings.options['acquisition']['interval']))
                        candidate = _metadata(raw, resolver, transport)
                        inventory = _inventory(client, namespace)
                        parent = _parents(candidate, inventory)
                        row.update(identity=_brief(candidate), network_reads=True,
                                   existing_parent=parent['key'] if parent else None,
                                   existing_pdf_keys=[a['key'] for a in _attachments(parent, inventory)])
                    rows.append(row)
                    continue
                token = _sha((namespace + '\n' + request_id).encode('utf-8'))
                directory = contained(settings.runtime, 'intake/workflows/' + token)
                row.update(_process(settings, raw, identity, namespace, directory, resume=resume,
                                    enabled=enabled or settings.options['acquisition']['enabled'],
                                    allow_create=allow_zotero_create, email=email, transport=transport,
                                    client=client, resolver=resolver, verifier=verifier,
                                    analysis=analysis, pause=pause, crash=crash, progress=progress))
                rows.append(row)
                _event(directory, 'item_finished', status=row['status'])
            except (ValueError, OSError, KeyError, TypeError, ImportError, HTTPException) as exc:
                code = exc.code if isinstance(exc, Blocked) else 'ITEM_FAILED'
                row = {**progress, 'index': index, 'input_sha256': _sha(raw.encode('utf-8')), 'status': code,
                       'exception_type': type(exc).__name__}
                if directory and directory.exists():
                    try:
                        _event(directory, 'item_blocked', status=code, exception_type=type(exc).__name__)
                    except (OSError, ValueError):
                        row['logging_failure'] = True
                rows.append(row)

    if apply:
        with _lock(contained(settings.runtime, 'intake')):
            execute()
    else:
        execute()
    successful = {'PLANNED', 'DUPLICATE_INPUT', 'ARCHIVED', 'ARCHIVED_ANALYSIS_PENDING'}
    blocked = sum(row['status'] not in successful for row in rows)
    return {'status': 'PARTIAL' if blocked else 'COMPLETE' if apply else 'PREVIEW',
            'applied': apply, 'library': namespace, 'selected': len(inputs), 'blocked': blocked,
            'items': rows, 'read_only': settings.read_only,
            'counts': {name: sum(int(row.get(name, 0)) for row in rows)
                       for name in ('parent_created', 'attachment_created', 'pdf_acquired', 'pdf_reused', 'zotero_read_back_verified')},
            'analysis_boundary': 'Automatic Notes remain partial; source-bound agent captures and human review are separate.',
            'existing_items_overwritten': 0, 'direct_sqlite_writes': 0}
