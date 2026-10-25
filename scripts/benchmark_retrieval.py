"""Offline two-layer retrieval measurement; plans are frozen before corpus access.

This maintenance runner measures lexical candidates. Final evidence relevance is
recorded by an agent after inspecting source pages, never inferred by filenames.
No user configuration, real library, network, or semantic backend is loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import _validation_common as common
from researchvault import fulltext, identity, validation
from researchvault.config import load_settings
from researchvault.documents import create_file, scan, write_new
from researchvault.safety import validation_output

ROOT = common.ROOT
B2 = common.GOLDEN / 'b2'
RELATIONS = {'direct_terms', 'exact_alias', 'related_concept', 'broader_concept',
             'narrower_concept', 'contrast_concept'}


digest = common.text_digest


def check_plans(plans, cases):
    if (plans.get('expected_answers_seen') is not False or
            plans.get('corpus_seen_before_plan') is not False or
            plans.get('plan_status') != 'frozen_before_execution'):
        raise ValueError('Plans must disclose answer and corpus blindness')
    expected = {c['request_id']: c['query'] for c in cases['cases']}
    rows = plans['plans']
    if len(rows) != len(expected) or {r['request_id'] for r in rows} != set(expected):
        raise ValueError('Query inventory differs')
    for row in rows:
        if row['original_query'] != expected[row['request_id']]:
            raise ValueError('Original query changed')
        if not 0 <= len(row['expansions']) <= 3 or not row['interpretation'].strip():
            raise ValueError('Expansion call budget exceeded or interpretation absent')
        for expansion in row['expansions']:
            if (expansion['relation'] not in RELATIONS or not expansion['query'].strip()
                    or not expansion['reason'].strip()):
                raise ValueError('Expansion relation or rationale absent')


def deduplicate(rows):
    """Attachments do not multiply papers; library namespace remains explicit."""
    unique = {}
    for row in rows:
        key = (row['library_id'], row['zotero_key'], row['source_version'])
        unique.setdefault(key, {'paper_id': row['paper_id'], 'library_id': key[0],
                               'zotero_key': key[1], 'source_version': key[2], 'paths': []})
        if row['path'] not in unique[key]['paths']:
            unique[key]['paths'].append(row['path'])
    return list(unique.values())


def acceptance(case, judgments, returned_papers):
    """Count evidence-supported answers, not merely a predetermined filename."""
    allowed = set(case['expected_relevant_papers'] + case['acceptable_relevant_papers'])
    supported = []
    for judgment in judgments:
        paper = judgment['paper_id']
        if paper not in returned_papers:
            raise ValueError('Reviewer accepted an unreturned paper')
        if judgment['verdict'] not in {'PASS', 'FAIL', 'UNCERTAIN', 'HUMAN_REVIEW_REQUIRED'}:
            raise ValueError('Invalid relevance verdict')
        if judgment['verdict'] == 'PASS':
            if not judgment.get('answer') or not judgment.get('evidence_anchor'):
                raise ValueError('Word matches cannot replace source evidence')
            if paper in allowed:
                supported.append(paper)
    return {'passed': bool(supported), 'accepted_papers': sorted(set(supported)),
            'frozen_target_found': bool(set(returned_papers) & set(case['expected_relevant_papers']))}


def numeric_regression(root=common.GOLDEN):
    # Freeze pins the comparison and source bytes using portable text digests.
    # Keep the original quantity mappings and numerical checker unchanged.
    annotations, captures = common.original_inputs(root)
    return common.compare_reviewed_numbers(annotations, captures, common.read_json(root / 'comparison.json'))


def check_recorded_benchmark(root=ROOT):
    """Replay recorded judgments' accounting; never rerun a semantic judge."""
    b2 = Path(root) / 'validation/golden/b2'
    common.verify_freeze(root)
    cases, plans = common.read_json(b2 / 'retrieval_cases.json'), common.read_json(b2 / 'retrieval_plans.json')
    check_plans(plans, cases)
    lock = common.read_json(b2 / 'retrieval_lock.json')
    if (lock['plans_digest'] != digest(b2 / 'retrieval_plans.json') or
            lock['cases_digest'] != digest(b2 / 'retrieval_cases.json') or
            lock['locked_before_execution'] is not True):
        raise ValueError('Retrieval measuring inputs changed')
    observed = common.read_json(b2 / 'retrieval_observed.json')
    review = common.read_json(b2 / 'retrieval_captures.json')
    if (review['review_kind'] != 'agent_review' or review['human_review_status'] != 'pending'
            or review['expected_answers_seen'] is not False
            or review['plan_mutated_after_execution'] is not False):
        raise ValueError('Retrieval review provenance differs')
    if observed['plans_digest'] != lock['plans_digest'] or observed['cases_digest'] != lock['cases_digest']:
        raise ValueError('Observed run used different inputs')
    _, captures = common.original_inputs(Path(root) / 'validation/golden')
    papers = {p['paper_id']: p for p in common.read_json(b2 / 'freeze.json')['papers']}
    requests = {r['request_id']: r for r in observed['requests']}
    reviewed = {r['request_id']: r for r in review['requests']}
    expected = {c['request_id'] for c in cases['cases']}
    if (set(requests) != expected or set(reviewed) != expected or
            len(observed['requests']) != len(expected) or len(review['requests']) != len(expected)):
        raise ValueError('Benchmark request inventory differs')
    packet = [{'request_id': r['request_id'], 'query': r['raw']['query'],
               'returned_papers': [u['paper_id'] for u in r['skill_candidates']],
               'sources': [{'paper_id': u['paper_id'], 'title': captures[u['paper_id']]['title'],
                            'pdf_filename': common.PDF_NAMES[u['paper_id']],
                            'pdf_sha256': papers[u['paper_id']]['pdf_sha256'],
                            'captured_claims': captures[u['paper_id']]['claims']}
                           for u in r['skill_candidates']]} for r in observed['requests']]
    packet_bytes = (json.dumps(packet, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if review['input_packet_digest'] != hashlib.sha256(packet_bytes).hexdigest():
        raise ValueError('Reviewer input packet no longer matches the observed corpus')
    results = []
    for case in cases['cases']:
        request = requests[case['request_id']]
        plan = next(p for p in plans['plans'] if p['request_id'] == case['request_id'])
        if [c['query'] for c in request['skill_calls']] != [plan['original_query']] + [e['query'] for e in plan['expansions']]:
            raise ValueError('Executed query plan changed')
        if request['raw'] != request['skill_calls'][0] or request['raw']['query'] != case['query']:
            raise ValueError('Original raw measurement changed')
        union = deduplicate([h for c in request['skill_calls'] for h in c['returned_documents']])
        if union != request['skill_candidates']:
            raise ValueError('Candidate deduplication changed')
        judgments = reviewed[case['request_id']]['judgments']
        candidates = [u['paper_id'] for u in union]
        if {j['paper_id'] for j in judgments} != set(candidates) or len(judgments) != len(candidates):
            raise ValueError('Every returned candidate must be reviewed once')
        for judgment in judgments:
            anchor = judgment.get('evidence_anchor')
            paper = papers[judgment['paper_id']]
            if (not isinstance(anchor, dict) or anchor.get('pdf_sha256') != paper['pdf_sha256']
                    or type(anchor.get('pdf_page')) is not int
                    or not 1 <= anchor['pdf_page'] <= paper['pdf_pages'] or not anchor.get('locator')):
                raise ValueError('Relevance source anchor differs from frozen paper')
        skill = acceptance(case, judgments, candidates)
        raw_candidates = {r['paper_id'] for r in request['raw']['returned_documents']}
        raw = acceptance(case, [j for j in judgments if j['paper_id'] in raw_candidates], raw_candidates)
        results.append({'case_id': case['case_id'], 'request_id': case['request_id'],
                        'query': case['query'], 'raw': raw, 'skill': skill})
    return {'format': 1, 'review_kind': 'agent_review', 'human_review_status': 'pending',
            'semantic_judgment_performed_by_checker': False, 'requests': results,
            'raw_passed': sum(r['raw']['passed'] for r in results),
            'skill_passed': sum(r['skill']['passed'] for r in results), 'total': len(results),
            'observed_digest': digest(b2 / 'retrieval_observed.json'),
            'captures_digest': digest(b2 / 'retrieval_captures.json'),
            'numerical_regression': numeric_regression(Path(root) / 'validation/golden'), 'new_backend': None,
            'embeddings_introduced': False, 'vector_database_introduced': False}


def run(papers_dir, plans_path, cases_path=B2 / 'retrieval_cases.json'):
    common.verify_freeze(ROOT, papers_dir=papers_dir)
    lock = common.read_json(B2 / 'retrieval_lock.json')
    if (lock['locked_before_execution'] is not True or
            lock['plans_digest'] != digest(plans_path) or
            lock['cases_digest'] != digest(cases_path)):
        raise ValueError('Frozen retrieval plan or relevance requirement changed')
    plans, cases = common.read_json(plans_path), common.read_json(cases_path)
    check_plans(plans, cases)
    annotations, captures = common.original_inputs()
    source_hashes = {p: common.raw_digest(Path(papers_dir) / f) for p, f in common.PDF_NAMES.items()}
    reports, packets = [], []
    with tempfile.TemporaryDirectory(prefix='researchvault-retrieval-') as temp:
        workspace = Path(temp).resolve()
        vault = workspace / 'isolated-vault'
        vault.mkdir()
        config = workspace / 'isolated.yaml'
        create_file(config, 'schema_version: 2\nread_only: false\n')
        settings = load_settings(config_path=config, vault=vault, cwd=workspace)
        fulltext.initialize(settings, apply=True)
        readonly = load_settings(config_path=config, vault=vault, cwd=workspace, read_only=True)
        path_paper = {}
        for index, (paper, filename) in enumerate(common.PDF_NAMES.items(), 1):
            capture = captures[paper]
            source = workspace / filename
            source.write_bytes((Path(papers_dir) / filename).read_bytes())
            record = {'library_id': None, 'zotero_key': f'GOLD{index:04}',
                      'pdf_key': f'PDFG{index:04}', 'title': capture['title'],
                      'doi': capture['doi'], 'arxiv_id': capture['arxiv_id']}
            selected = identity.select([record], zotero_key=record['zotero_key'],
                                       publication_doi=capture['doi'], arxiv_id=capture['arxiv_id'])
            note = '02-papers/Other/' + record['zotero_key'] + '.md'
            archived = fulltext.archive(settings, selected, source, method='pdf', note_path=note, apply=True)
            data = {**record, 'schema_version': 2, 'type': 'literature-note',
                    'read_status': 'complete', 'evidence_status': 'pdf_verified',
                    'identity_origin': 'validation fixture; not a real Zotero item',
                    'human_reviewed': False, 'source_version': capture['source_version'],
                    'pdf_path': str(source), 'fulltext_path': archived['path'],
                    'claim_ids': [c['id'] for c in capture['claims']]}
            body = '\n\n'.join(c['statement'] + '\nScope: ' + c['scope'] for c in capture['claims'])
            write_new(settings.resolve(note), data, body + '\n\n[[' + archived['path'] + ']]\n')
            for claim in capture['claims']:
                claim_data = {'schema_version': 2, 'claim_id': claim['id'],
                              'text': claim['statement'], 'page_path': note,
                              'source_notes': [note], 'source_papers': [record['zotero_key']],
                              'evidence_status': 'pdf_verified', 'scope': claim['scope'],
                              'verification': [{**{k: record[k] for k in ('zotero_key', 'pdf_key', 'library_id')},
                                                'fulltext_path': archived['path'], 'method': 'pdf',
                                                'locator': {'pdf_page': claim['pdf_page'], 'section': claim['locator']},
                                                'observation': claim['statement']}]}
                claim_path = settings.resolve(settings.options['paths']['metadata'] + '/claims/' + claim['id'] + '.json')
                create_file(claim_path, json.dumps(claim_data, ensure_ascii=False))
            path_paper[note] = path_paper[archived['path']] = paper
        records = {r.relative: r for r in scan(readonly)}
        baseline = validation.validate(readonly)
        if not baseline['valid']:
            raise ValueError('Isolated source corpus failed structural validation')
        before = {p.relative_to(vault): common.raw_digest(p) for p in vault.rglob('*') if p.is_file()}

        def call(query):
            result = fulltext.retrieve(readonly, query)
            rows = []
            for rank, hit in enumerate(result['matches'], 1):
                record = records[hit['path']]
                content = (str(record.data.get('title', '')) + '\n' + record.body).casefold()
                rows.append({**hit, 'paper_id': path_paper[hit['path']], 'rank': rank,
                             'matched_terms': [t for t in query.casefold().split() if t in content],
                             'library_id': record.data.get('library_id'),
                             'zotero_key': record.data['zotero_key'],
                             'source_version': captures[path_paper[hit['path']]]['source_version']})
            return {'query': query, 'layers': result['layers'], 'returned_documents': rows,
                    'rank_semantics': 'path traversal order; no semantic relevance score'}

        for plan in plans['plans']:
            raw = call(plan['original_query'])
            # The unchanged primitive already gates Fulltext on empty Note recall.
            calls = [raw] + [call(e['query']) for e in plan['expansions']]
            union = deduplicate([h for c in calls for h in c['returned_documents']])
            reports.append({'request_id': plan['request_id'], 'raw': raw,
                            'skill_calls': calls, 'skill_candidates': union})
            packets.append({'request_id': plan['request_id'], 'query': plan['original_query'],
                            'returned_papers': [u['paper_id'] for u in union],
                            'sources': [{'paper_id': u['paper_id'],
                                         'title': captures[u['paper_id']]['title'],
                                         'pdf_filename': common.PDF_NAMES[u['paper_id']],
                                         'pdf_sha256': source_hashes[u['paper_id']],
                                         'captured_claims': captures[u['paper_id']]['claims']} for u in union]})
        after = {p.relative_to(vault): common.raw_digest(p) for p in vault.rglob('*') if p.is_file()}
        if before != after:
            raise ValueError('Read-only retrieval mutated the isolated Vault')
    if source_hashes != {p: common.raw_digest(Path(papers_dir) / f) for p, f in common.PDF_NAMES.items()}:
        raise ValueError('Source PDFs changed')
    return {'format': 1, 'plans_digest': digest(plans_path), 'cases_digest': digest(cases_path),
            'corpus': 'three frozen captures as Notes and three hashed Fulltexts; no Knowledge fixtures',
            'baseline_valid': baseline['valid'], 'read_only_unchanged': True,
            'real_zotero_writes': 0, 'real_obsidian_mutations': 0, 'requests': reports}, packets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-recorded', action='store_true')
    parser.add_argument('--papers-dir', type=Path)
    parser.add_argument('--plans', type=Path, default=B2 / 'retrieval_plans.json')
    parser.add_argument('--output-workspace', type=Path)
    args = parser.parse_args()
    try:
        if args.check_recorded:
            report = check_recorded_benchmark()
            stored = common.read_json(B2 / 'retrieval_results.json')
            if report != stored:
                raise ValueError('Recorded benchmark result is stale')
            print(json.dumps({'record_contract_valid': True, 'raw': report['raw_passed'],
                              'skill': report['skill_passed'], 'total': report['total'],
                              'semantic_judgment_performed': False, 'human_review_status': 'pending'}))
            return 0
        if args.papers_dir is None or args.output_workspace is None:
            parser.error('--papers-dir and --output-workspace are required to measure recall')
        report, packet = run(args.papers_dir, args.plans)
        for name, data in [('retrieval_observed.json', report), ('retrieval_returned.private.json', packet)]:
            path = validation_output(args.output_workspace, name, protected_roots=[args.papers_dir])
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
        print(json.dumps({'measured_requests': len(report['requests']),
                          'baseline_valid': report['baseline_valid'], 'semantic_acceptance': 'pending'}))
        return 0
    except Exception as exc:
        print(json.dumps({'error': type(exc).__name__, 'detail': 'Inspect explicit local inputs.'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
