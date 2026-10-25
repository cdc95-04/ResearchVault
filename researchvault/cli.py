"""Explicit commands around the library; network actions are never implicit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .config import configured_read_only, contained, load_settings
from .documents import load_yaml, scan


def _input(path):
    return load_yaml(Path(path).read_text(encoding='utf-8-sig'))


def parser():
    root = argparse.ArgumentParser(prog='researchvault', description=f'Explicit research evidence workflow; project {__version__}, Vault schema 2')
    root.add_argument('--version', action='version', version=__version__)
    root.add_argument('--config', help='Configuration file; relative roots use its directory')
    root.add_argument('--vault', help='Explicit Vault root; overrides configuration')
    root.add_argument('--synthetic', action='store_true', help='Explicitly permit fixture roots inside allowed repository locations')
    root.add_argument('--read-only', action='store_true', help='Validation mode: block Zotero mutations, Vault writes, acquisition and eval file output')
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('validate', help='Read-only evidence and scientific record validation')
    init = commands.add_parser('init', help='Preview missing folders and templates')
    init.add_argument('--apply', action='store_true')
    resolve = commands.add_parser('resolve', help='Resolve existing local Note metadata')
    for name in ('zotero-key', 'pdf-key', 'doi', 'arxiv-id', 'title'):
        resolve.add_argument('--' + name)
    archive = commands.add_parser('archive', help='Preview an original-text archive; never generate interpretation')
    archive.add_argument('metadata', help='YAML/JSON source identity object')
    archive.add_argument('source', help='Existing original UTF-8 text or PDF file')
    archive.add_argument('--method', choices=('text', 'cache', 'structured', 'pdf'), default='text')
    archive.add_argument('--note-path', help='Intended Vault-relative Note path')
    archive.add_argument('--apply', action='store_true')
    retrieve = commands.add_parser('retrieve', help='Search local Notes/Knowledge, then optional Fulltext')
    retrieve.add_argument('query'); retrieve.add_argument('--supplementary', action='store_true')
    ingest = commands.add_parser('ingest', help='Selected batch source archive; retain blocked items',
                                 description='Selected batch source archive: creates Fulltext archives from supplied sources, '
                                             'retaining blocked items. Does not generate Paper Notes or analysis.')
    ingest.add_argument('batch', help='YAML/JSON list of explicitly selected source records')
    ingest.add_argument('--apply', action='store_true')
    commands.add_parser('migration-plan', help='Read-only manual schema migration inventory')
    diff = commands.add_parser('diff', help='Show proposed page changes without applying them')
    diff.add_argument('path'); diff.add_argument('proposed')
    for name in ('claim-lock', 'design-lock', 'corpus-freeze', 'snapshot'):
        lock = commands.add_parser(name, help='Preview an immutable receipt and proposed page metadata')
        lock.add_argument('path', help='Vault-relative source record')
        lock.add_argument('--apply', action='store_true'); lock.add_argument('--previous'); lock.add_argument('--reason')
        if name in ('claim-lock', 'design-lock'):
            lock.add_argument('--timing', choices=('pre-result', 'post-result'), default='pre-result')
        if name == 'snapshot':
            lock.add_argument('--input', action='append', default=[])
            lock.add_argument('--source', action='append', default=[])
    discover = commands.add_parser('discover', help='Query public Crossref metadata; explicitly performs network reads')
    discover.add_argument('query'); discover.add_argument('--limit', type=int)
    acquire = commands.add_parser('acquire', help='Selected lawful OA intake; requires configured runtime and enable switch')
    acquire.add_argument('candidates'); acquire.add_argument('--select', action='append', required=True, help='Selected DOI; repeat for an explicit batch')
    acquire.add_argument('--enable', action='store_true'); acquire.add_argument('--email')
    intake = commands.add_parser('intake', help='Selected DOI/arXiv/official URL workflow; offline preview by default')
    intake.add_argument('identifiers', nargs='+', help='Explicit selected identifiers; no discovery or batch expansion')
    mode = intake.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Explicit preview; default mode')
    mode.add_argument('--apply', action='store_true', help='Create new runtime/Vault assets; respects read_only')
    intake.add_argument('--resolve', action='store_true', help='Preview with public metadata and read-only Zotero dedup; no PDF downloads')
    intake.add_argument('--enable', action='store_true', help='Enable lawful acquisition for this operation only')
    intake.add_argument('--allow-zotero-create', action='store_true', help='Explicitly authorize create-only Zotero writes; a key is still required')
    intake.add_argument('--email', help='Explicit Unpaywall contact for DOI routes; never saved in logs')
    intake.add_argument('--resume', action='store_true', help='Resume frozen metadata and durable receipts; never retry an uncertain write')
    intake.add_argument('--analysis', help='JSON/YAML mapping canonical IDs to PDF-hash/page/quote-bound analysis captures')
    for name in ('zotero-inventory', 'zotero-resolve', 'zotero-create', 'zotero-import'):
        command = commands.add_parser(name, help='Explicit Zotero Local API operation')
        if name == 'zotero-resolve':
            for key in ('zotero-key', 'pdf-key', 'doi'):
                command.add_argument('--' + key)
        if name in ('zotero-create', 'zotero-import'):
            command.add_argument('metadata'); command.add_argument('--apply', action='store_true')
            command.add_argument('--receipt', help='Runtime-relative durable mutation-intent receipt; requires runtime_dir and is mandatory for apply')
        if name == 'zotero-import':
            command.add_argument('parent'); command.add_argument('pdf')
    evaluate = commands.add_parser('eval-run', help='Evaluate captured outputs; not a real-paper benchmark unless reviewed')
    evaluate.add_argument('suite'); evaluate.add_argument('captures'); evaluate.add_argument('--output')
    compare = commands.add_parser('eval-compare', help='Compare compatible captured-output evaluations')
    compare.add_argument('left'); compare.add_argument('right')
    numbers = commands.add_parser('numbers', help='Compare explicit numeric claim mappings')
    numbers.add_argument('input')
    return root


def dispatch(args):
    name = args.command
    if name.startswith('eval-') or name == 'numbers':
        from . import evaluation
        if name == 'eval-run':
            if args.output and configured_read_only(args.config, read_only=args.read_only):
                raise ValueError('Evaluation file output is blocked in read-only validation mode; use stdout')
            return evaluation.run(args.suite, args.captures, output_path=args.output)
        if name == 'eval-compare':
            return evaluation.compare(_input(args.left), _input(args.right))
        return evaluation.numbers(_input(args.input))
    settings = load_settings(args.config, args.vault, args.synthetic, read_only=args.read_only)
    from . import fulltext
    if name == 'init':
        return fulltext.initialize(settings, args.apply)
    if name == 'validate':
        from .validation import validate
        return validate(settings)
    if name == 'resolve':
        from .identity import select
        return select([r.data for r in scan(settings) if r.type == 'literature-note'], zotero_key=args.zotero_key,
                      pdf_key=args.pdf_key, publication_doi=args.doi, arxiv_id=args.arxiv_id,
                      name=args.title, library_id=settings.options['zotero']['library_id'])
    if name == 'archive':
        return fulltext.archive(settings, _input(args.metadata), args.source, method=args.method, note_path=args.note_path, apply=args.apply)
    if name == 'retrieve':
        return fulltext.retrieve(settings, args.query, supplementary=args.supplementary)
    if name == 'ingest':
        return fulltext.ingest(settings, _input(args.batch), apply=args.apply)
    if name == 'migration-plan':
        return fulltext.migration(settings)
    if name == 'diff':
        return fulltext.diff(settings, args.path, args.proposed)
    if name in ('claim-lock', 'design-lock'):
        from .process import freeze
        return freeze(settings, args.path, name.split('-')[0], apply=args.apply, previous=args.previous, reason=args.reason, timing=args.timing)
    if name == 'corpus-freeze':
        from .review import freeze
        return freeze(settings, args.path, apply=args.apply, previous=args.previous, reason=args.reason)
    if name == 'snapshot':
        from .provenance import snapshot
        return snapshot(settings, args.path, inputs=args.input, sources=args.source, tool_version=__version__,
                        apply=args.apply, previous=args.previous, reason=args.reason)
    if name == 'discover':
        from .discovery import search
        if not settings.options['discovery']['enabled']:
            raise ValueError('Discovery is disabled in configuration')
        return search(args.query, rows=args.limit or settings.options['discovery']['limit'])
    if name == 'acquire':
        from .acquisition import run
        candidates = _input(args.candidates)
        if isinstance(candidates, dict):
            candidates = candidates.get('candidates')
        return run(settings, candidates, selected=args.select, enabled=args.enable or settings.options['acquisition']['enabled'], email=args.email)
    if name == 'intake':
        from .intake import run
        return run(settings, args.identifiers, apply=args.apply, resolve_metadata=args.resolve,
                   enabled=args.enable, allow_zotero_create=args.allow_zotero_create,
                   email=args.email, resume=args.resume,
                   analysis=_input(args.analysis) if args.analysis else None)
    if name.startswith('zotero-'):
        from .zotero import Client
        receipt = None
        if name in ('zotero-create', 'zotero-import'):
            if args.apply and not args.receipt:
                raise ValueError('Zotero writes require an explicit runtime-relative --receipt')
            if args.receipt:
                if settings.runtime is None:
                    raise ValueError('Zotero receipts require a configured external runtime_dir')
                receipt = contained(settings.runtime, args.receipt)
        group = settings.options['zotero']['library_id']
        client = Client('users/0' if group is None else f'groups/{group}', api_key_env=settings.options['zotero']['api_key_env'],
                        read_only=settings.read_only)
        if name == 'zotero-inventory':
            return client.inventory()
        if name == 'zotero-resolve':
            return client.find_pdf(zotero_key=args.zotero_key, pdf_key=args.pdf_key, doi=args.doi)
        if name == 'zotero-create':
            return client.create_item(_input(args.metadata), apply=args.apply, receipt_path=receipt)
        # Runtime/source containment is also required before a deliberate write.
        path = fulltext.original_file(settings, args.pdf)
        return client.import_pdf(args.parent, path, _input(args.metadata), apply=args.apply, receipt_path=receipt)
    raise ValueError('Unknown operation')


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str, allow_nan=False))
        failed = (result.get('valid') is False or result.get('passed') is False or bool(result.get('blocked'))
                  or result.get('status') in {'MANUAL_RECONCILIATION_REQUIRED', 'AMBIGUOUS', 'FAILED'})
        return 1 if failed else 0
    except (ValueError, OSError, ImportError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc), 'type': type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 2
