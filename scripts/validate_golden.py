"""Offline public-paper validation. No network or access to personal libraries.

Captures are independently authored answers, not generated golden expectations.
PDFs are supplied explicitly and copied into a fresh OS temporary workspace.
Only aggregate findings and minimal public facts may leave that workspace.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from researchvault import evaluation, fulltext, identity, process, validation
from researchvault.config import load_settings
from researchvault.documents import create_file, read_record, scan, write_new
from researchvault.safety import validation_output

GOLDEN = ROOT / 'validation' / 'golden'
PDF_NAMES = {'sac2018': 'sac2018.pdf',
             'diffusion_policy2023': 'diffusion_policy2023_rss.pdf',
             'sim2real2018': 'sim2real2018_arxiv_v3.pdf'}


def read_json(path):
    # The same strict reader rejects duplicate keys and nonfinite numbers.
    return evaluation._read(path)[0]


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs(root=GOLDEN):
    annotations, captures = {}, {}
    for paper_id in PDF_NAMES:
        annotation = read_json(root / 'annotations' / (paper_id + '.json'))
        capture = read_json(root / 'captures' / (paper_id + '.json'))
        if annotation['paper_id'] != paper_id or capture['paper_id'] != paper_id:
            raise ValueError('Paper identity differs from its input filename')
        if annotation['review']['human_reviewed'] or capture['human_reviewed']:
            raise ValueError('This candidate suite has no completed human review')
        if annotation['review']['implementation_outputs_seen'] or capture['golden_seen_before_capture']:
            raise ValueError('Candidate independence declaration is inconsistent')
        claim_ids = [claim['id'] for claim in annotation['claims']]
        captured_ids = [claim['id'] for claim in capture['claims']]
        if any(not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', key)
               for key in claim_ids + captured_ids):
            raise ValueError('Claim identities must be portable filename-safe identifiers')
        if (len(set(claim_ids)) != len(claim_ids) or len(set(captured_ids)) != len(captured_ids)
                or set(claim_ids) != set(captured_ids)):
            raise ValueError('Expected and captured claim inventories differ')
        for query in annotation['retrieval_queries']:
            if not query['query'].strip() or not set(query['expected_claim_ids']) <= set(claim_ids):
                raise ValueError('Predefined query has no valid target')
        annotations[paper_id], captures[paper_id] = annotation, capture
    return annotations, captures


def reviewed_comparison(root=GOLDEN):
    comparison = read_json(root / 'comparison.json')
    manifest = comparison.get('input_manifest', [])
    if len(manifest) != len(PDF_NAMES) or {row['paper_id'] for row in manifest} != set(PDF_NAMES):
        raise ValueError('Comparison must identify every reviewed input')
    for row in manifest:
        for folder, field in [('annotations', 'annotation_sha256'), ('captures', 'capture_sha256')]:
            source = root / folder / (row['paper_id'] + '.json')
            if fingerprint(source) != row.get(field):
                raise ValueError('Comparison is stale for a reviewed input')
    return comparison


def compare_numbers(annotations, captures, comparison):
    """Use reviewed condition mappings; never align numbers merely by value."""
    results = []
    for row in comparison['records']:
        paper, key = row['paper_id'], row['claim_id']
        golden = next(c for c in annotations[paper]['claims'] if c['id'] == key)
        captured = next(c for c in captures[paper]['claims'] if c['id'] == key)
        names = {n['name']: n for n in captured['numbers']}
        mapped = set()
        for mapping in row['numeric_mappings']:
            index = mapping['golden_index']
            if type(index) is not int or index in mapped or not mapping['mapping_reason'].strip():
                raise ValueError('Numeric mapping must be unique and explain conditions')
            mapped.add(index)
            expected = golden['numeric_facts'][index]
            observed = names[mapping['capture_name']]
            # Units are semantically aligned in the separate review, not silently
            # converted here. The value check retains exact numeric agreement.
            checked = evaluation.numbers([{'claim_id': key + ':' + str(index),
                'unit': expected['unit'], 'required_locations': ['source_annotation', 'capture'],
                'occurrences': [
                    {'location': 'source_annotation', 'value': expected['value'], 'unit': expected['unit']},
                    {'location': 'capture', 'value': observed['value'], 'unit': expected['unit']}]}])
            results.append({'paper_id': paper, 'claim_id': key, 'golden_index': index,
                            'capture_name': mapping['capture_name'], 'passed': checked['passed']})
        if mapped != set(range(len(golden['numeric_facts']))):
            raise ValueError('Every independent numeric expectation needs a reviewed mapping')
    expected_keys = {(p, c['id']) for p, a in annotations.items() for c in a['claims']}
    actual_keys = [(r['paper_id'], r['claim_id']) for r in comparison['records']]
    if len(set(actual_keys)) != len(actual_keys) or set(actual_keys) != expected_keys:
        raise ValueError('Comparison must cover every claim exactly once')
    return {'matched': sum(r['passed'] for r in results), 'total': len(results), 'checks': results,
            'unit_and_condition_review': 'agent reviewed explicit mappings, pending human acceptance'}


def _rejected(action):
    try:
        action()
    except ValueError:
        return True
    return False


def run(papers_dir, root=GOLDEN):
    annotations, captures = inputs(root)
    comparison = reviewed_comparison(root)
    numeric = compare_numbers(annotations, captures, comparison)
    reports, injections, queries = [], [], []
    source_hashes = {}
    with tempfile.TemporaryDirectory(prefix='researchvault-golden-') as temporary:
        workspace = Path(temporary).resolve()
        vault = workspace / 'isolated-vault'
        vault.mkdir()
        config = workspace / 'validation.yaml'
        create_file(config, 'schema_version: 2\nread_only: false\n')
        settings = load_settings(config_path=config, vault=vault, cwd=workspace)
        # This instance permits writes only to our newly-created isolated Vault.
        # User sources are never loaded; verification gets a read-only instance.
        fulltext.initialize(settings, apply=True)
        readonly = load_settings(config_path=config, vault=vault, cwd=workspace, read_only=True)
        records, claims = {}, {}
        for index, paper_id in enumerate(PDF_NAMES, 1):
            annotation, capture = annotations[paper_id], captures[paper_id]
            original = Path(papers_dir).resolve() / PDF_NAMES[paper_id]
            source_hashes[paper_id] = fingerprint(original)
            if source_hashes[paper_id] != annotation['pdf_sha256']:
                raise ValueError('PDF digest differs from the version independently annotated: ' + paper_id)
            source = workspace / PDF_NAMES[paper_id]
            source.write_bytes(original.read_bytes())
            parent, attachment = f'GOLD{index:04}', f'PDFG{index:04}'
            record = {'library_id': None, 'zotero_key': parent, 'pdf_key': attachment,
                      'title': capture['title'], 'doi': capture['doi'], 'arxiv_id': capture['arxiv_id']}
            records[paper_id] = record
            selected = identity.select([record], zotero_key=parent,
                                       publication_doi=capture['doi'], arxiv_id=capture['arxiv_id'])
            note_path = '02-papers/Other/' + parent + '.md'
            archived = fulltext.archive(settings, selected, source, method='pdf', note_path=note_path, apply=True)
            fulltext_path = archived['path']
            note_data = {**record, 'schema_version': 2, 'type': 'literature-note',
                         'read_status': 'complete', 'evidence_status': 'pdf_verified',
                         'identity_origin': 'validation fixture; not a real Zotero item',
                         'human_reviewed': False, 'source_version': capture['source_version'],
                         'pdf_path': str(source), 'fulltext_path': fulltext_path,
                         'claim_ids': [c['id'] for c in capture['claims']]}
            body = '\n\n'.join(c['statement'] + '\nScope: ' + c['scope'] for c in capture['claims'])
            body += '\n\n[[' + fulltext_path + ']]\n'
            write_new(settings.resolve(note_path), note_data, body)
            for claim in capture['claims']:
                data = {'schema_version': 2, 'claim_id': claim['id'], 'text': claim['statement'],
                        'page_path': note_path, 'source_notes': [note_path], 'source_papers': [parent],
                        'evidence_status': 'pdf_verified', 'scope': claim['scope'],
                        'verification': [{'zotero_key': parent, 'pdf_key': attachment, 'library_id': None,
                            'fulltext_path': fulltext_path, 'method': 'pdf',
                            'locator': {'pdf_page': claim['pdf_page'], 'section': claim['locator']},
                            'observation': claim['statement']}]}
                path = settings.resolve(settings.options['paths']['metadata'] + '/claims/' + claim['id'] + '.json')
                create_file(path, json.dumps(data, ensure_ascii=False))
                claims[claim['id']] = data
            # Published results are literature, never an experiment we performed.
            ledger_path = '08-writing/Claims/' + paper_id + '.md'
            ledger = {'schema_version': 2, 'type': 'claim-ledger', 'claim_id': paper_id + '-literature',
                      'verdict': 'NOT_TESTED', 'result_ids': [], 'literature': [note_path],
                      'evidence_ceiling': {key: [] for key in process.CEILINGS},
                      'published_result_claims': [c['id'] for c in capture['claims']],
                      'human_reviewed': False}
            write_new(settings.resolve(ledger_path), ledger,
                      'Published evidence only. No local reproduction trials were performed.\n\n' + body)
            stored = read_record(settings.resolve(fulltext_path), vault)
            reused = fulltext.archive(settings, selected, source, method='pdf', note_path=note_path, apply=True)
            reports.append({'paper_id': paper_id, 'identity_origin': 'synthetic parent/attachment keys',
                            'real_zotero_binding': 'not_covered', 'pdf_sha256': source_hashes[paper_id],
                            'pdf_pages': len(__import__('pypdf').PdfReader(source).pages),
                            'archive_body_digest_matches': hashlib.sha256(stored.body.encode()).hexdigest() == stored.data['text_sha256'],
                            'original_bytes_preserved': fingerprint(source) == source_hashes[paper_id],
                            'repeat_archive_reused': reused['reused'],
                            'note_path': note_path, 'fulltext_path': fulltext_path,
                            'ledger_verdict': ledger['verdict']})

        baseline = validation.validate(readonly)
        scanned = scan(readonly)
        for paper_id, annotation in annotations.items():
            report = next(r for r in reports if r['paper_id'] == paper_id)
            for query in annotation['retrieval_queries']:
                result = fulltext.retrieve(readonly, query['query'])
                expected_paths = {report['note_path'], report['fulltext_path']}
                target_hits = [r for r in result['matches'] if r['path'] in expected_paths]
                queries.append({'paper_id': paper_id, **query, 'relevant_paper_found': bool(target_hits),
                                'matched_paths': [r['path'] for r in result['matches']],
                                'granularity': 'paper-level; engine does not rank individual claims'})
            record = records[paper_id]

            def injected(name, detected, category, mechanism):
                injections.append({'paper_id': paper_id, 'name': name, 'expected_invalid': True,
                                   'detected': detected, 'category': category, 'mechanism': mechanism})

            injected('selected_parent_doi_conflict', _rejected(lambda: identity.select([record],
                     zotero_key=record['zotero_key'], publication_doi='10.9999/deliberately-conflicting')),
                     'identity', 'explicit parent selection with a DOI absent from or conflicting with its metadata')
            injected('arxiv_version_conflict', _rejected(lambda: identity.select([record], zotero_key=record['zotero_key'],
                     arxiv_id=record['arxiv_id'] + ('1' if 'v' in record['arxiv_id'] else 'v99'))),
                     'identity', 'explicit mismatched preprint version')
            duplicate = dict(record, zotero_key='DUPL0001', pdf_key='DUPF0001')
            injected('duplicate_identifier', _rejected(lambda: identity.check_records([record, duplicate])),
                     'identity', 'same external identifier assigned to two parents')

            text_file = settings.resolve(report['fulltext_path'])
            before = text_file.read_bytes()
            try:
                with text_file.open('ab') as stream:
                    stream.write(b'\nDeliberate isolated text drift.\n')
                codes = {d['code'] for d in validation.validate(readonly)['diagnostics']}
                injected('fulltext_drift', 'FULLTEXT_DRIFT' in codes, 'integrity', 'changed only the temporary archived body')
            finally:
                text_file.write_bytes(before)

            old_link = ('note_path: ' + report['note_path']).encode()
            if before.count(old_link) != 1:
                raise ValueError('Cannot isolate the reciprocal-link mutation')
            try:
                text_file.write_bytes(before.replace(old_link, b'note_path: missing.md', 1))
                codes = {d['code'] for d in validation.validate(readonly)['diagnostics']}
                injected('reciprocal_link', 'RECIPROCAL_LINK' in codes, 'linkage',
                         'Vault validator on an altered temporary Fulltext backlink')
            finally:
                text_file.write_bytes(before)

            original_claim = claims[annotation['claims'][-1]['id']]
            for name, mutator, category in [
                ('impossible_page', lambda c: c['verification'][0]['locator'].update(pdf_page=1000000), 'provenance'),
                ('fabricated_quote', lambda c: c['verification'][0].update(quote='UNSUPPORTED-GOLDEN-QUOTE-83fd92'), 'provenance'),
                ('wrong_numeric_observation', lambda c: c['verification'][0].update(observation='The reported success rate is 98765 percent.'), 'semantic'),
                ('overbroad_scope', lambda c: c.update(scope='Proves universal success on every robot and task.'), 'semantic'),
                ('wrong_table_condition', lambda c: c['verification'][0].update(observation='These measurements are from every physical robot with unseen tasks.'), 'semantic')]:
                bad = copy.deepcopy(original_claim)
                mutator(bad)
                issues = validation.verify_claim(readonly, bad, scanned)
                expected_code = {'impossible_page': 'FABRICATED_PAGE',
                                 'fabricated_quote': 'FABRICATED_QUOTE'}.get(name)
                if expected_code:
                    detected = any(d['code'] == expected_code and d['path'] == bad['page_path'] for d in issues)
                else:
                    # No semantic decision exists in verify_claim. Unrelated
                    # structural diagnostics are unscored, never true positives.
                    detected = False if not issues else None
                injected(name, detected, category, 'page-bound observation and claim binding check')
                injections[-1]['diagnostic_codes'] = [d['code'] for d in issues]

            ledger = next(r for r in scanned if r.type == 'claim-ledger' and r.data['claim_id'] == paper_id + '-literature')
            ledger.data['verdict'] = 'SUPPORTED'
            injected('literature_as_supported', any(d['code'] == 'science.claim-ledger'
                     and d['path'] == ledger.relative and 'literature cannot establish' in d['detail']
                     for d in process.check(readonly, scanned)), 'accounting',
                     'published results cannot establish an experimental ledger verdict')
            ledger.data['verdict'] = 'NOT_TESTED'

        after = validation.validate(readonly)
        for paper_id in PDF_NAMES:
            if fingerprint(Path(papers_dir) / PDF_NAMES[paper_id]) != source_hashes[paper_id]:
                raise ValueError('Input PDF changed during validation')
    return {'format': 1, 'real_source_papers': 3, 'human_reviewed': False,
            'status': 'candidate_with_known_gaps', 'phase_c_gate': 'not_met',
            'real_zotero_writes': 0, 'real_obsidian_modifications': 0,
            'input_digests': {str(p.relative_to(root)).replace('\\', '/'): fingerprint(p)
                             for p in sorted(root.rglob('*.json')) if 'reports' not in p.parts},
            'papers': reports, 'baseline': baseline, 'restored_baseline_valid': after['valid'],
            'numeric_consistency': numeric, 'retrieval': queries,
            'retrieval_relevant_papers_found': sum(q['relevant_paper_found'] for q in queries),
            'retrieval_query_count': len(queries), 'injections': injections,
            'injected_errors_detected': sum(i['detected'] is True for i in injections),
            'injected_errors_unscored': sum(i['detected'] is None for i in injections),
            'injected_error_count': len(injections),
            'limitations': ['Independent agent annotations and blind agent captures, not human ground truth.',
                           'Identity/intake use explicit fixture keys; no real Zotero item exists.',
                           'Validator establishes structural provenance, not observation entailment.',
                           'Published results remain literature; no local experimental Result Bundle was fabricated.',
                           'The phase-one eval-run remains synthetic-only; this separate runner measures public-paper integration.']}


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--papers-dir', type=Path)
    parser.add_argument('--check-inputs', action='store_true')
    parser.add_argument('--output-workspace', type=Path)
    args = parser.parse_args()
    if args.check_inputs:
        annotations, captures = inputs()
        numeric = compare_numbers(annotations, captures, reviewed_comparison())
        report = {'input_contract_valid': True, 'papers': len(annotations), 'numeric_consistency': numeric,
                  'pdf_integration_executed': False, 'human_reviewed': False}
    else:
        if args.papers_dir is None:
            parser.error('--papers-dir is required for offline PDF integration')
        report = run(args.papers_dir)
    if args.output_workspace:
        target = validation_output(args.output_workspace, 'golden-report.json',
                                   protected_roots=([args.papers_dir] if args.papers_dir else []))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # Producing a report successfully is not acceptance of the benchmark.
    # Exit failure for measured errors/gaps; --check-inputs is only a contract check.
    if args.check_inputs:
        return 0 if report['numeric_consistency']['matched'] == report['numeric_consistency']['total'] else 1
    return 0 if (report['baseline']['valid'] and report['restored_baseline_valid'] and
                 report['numeric_consistency']['matched'] == report['numeric_consistency']['total'] and
                 report['retrieval_relevant_papers_found'] == report['retrieval_query_count'] and
                 report['injected_errors_detected'] == report['injected_error_count']) else 1


def main():
    try:
        return _main()
    except Exception as exc:
        # Input paths may be private even when the supplied papers are public.
        # Keep failures actionable by type without exporting traceback/source data.
        print(json.dumps({'validation_error': type(exc).__name__,
                          'details': 'Validation stopped; inspect explicit inputs locally.'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
