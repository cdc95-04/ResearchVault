"""Observed failures must be measured at the right retrieval layer."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import benchmark_retrieval as benchmark


class RetrievalBoundary(unittest.TestCase):
    def setUp(self):
        self.cases = {'cases': [{'request_id': 'query', 'query': 'future movement?',
                                'expected_relevant_papers': ['target'],
                                'acceptable_relevant_papers': ['alternative']}]}
        self.plans = {'expected_answers_seen': False, 'corpus_seen_before_plan': False,
                      'plan_status': 'frozen_before_execution', 'plans': [
                          {'request_id': 'query', 'original_query': 'future movement?',
                           'interpretation': 'Observation-responsive sequence prediction.',
                           'expansions': [{'query': 'receding horizon',
                                           'relation': 'narrower_concept',
                                           'reason': 'One possible execution mechanism.'}]}]}

    def test_plan_cannot_replace_the_original_query_or_exceed_call_budget(self):
        benchmark.check_plans(self.plans, self.cases)
        for mutation in ('query', 'budget', 'answer-seen', 'corpus-seen', 'relation'):
            plan = copy.deepcopy(self.plans)
            row = plan['plans'][0]
            if mutation == 'query':
                row['original_query'] = 'expected-paper-title'
            elif mutation == 'budget':
                row['expansions'] *= 4
            elif mutation == 'answer-seen':
                plan['expected_answers_seen'] = True
            elif mutation == 'corpus-seen':
                plan['corpus_seen_before_plan'] = True
            else:
                row['expansions'][0]['relation'] = 'equivalent_by_default'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                benchmark.check_plans(plan, self.cases)

    def test_relevance_needs_inspected_evidence_and_allows_alternative_sources(self):
        case = self.cases['cases'][0]
        self.assertFalse(benchmark.acceptance(case, [], ['target'])['passed'])
        review = {'paper_id': 'alternative', 'verdict': 'PASS',
                  'answer': 'Source-supported bounded execution and replanning.',
                  'evidence_anchor': {'pdf_page': 3, 'locator': 'Method'}}
        result = benchmark.acceptance(case, [review], ['alternative'])
        self.assertTrue(result['passed'])
        self.assertFalse(result['frozen_target_found'])
        for mutation in ('missing-evidence', 'unreturned-paper'):
            changed = copy.deepcopy(review)
            if mutation == 'missing-evidence':
                changed.pop('evidence_anchor')
            else:
                changed['paper_id'] = 'unreturned'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                benchmark.acceptance(case, [changed], ['alternative'])

    def test_dedup_preserves_library_namespace_and_source_version(self):
        rows = [{'library_id': None, 'zotero_key': 'SAME0001', 'source_version': 'v1',
                 'paper_id': 'paper', 'path': path} for path in ('note.md', 'fulltext.md')]
        rows.append({**rows[0], 'library_id': 2, 'path': 'group-note.md'})
        rows.append({**rows[0], 'source_version': 'v2', 'path': 'revised.md'})
        result = benchmark.deduplicate(rows)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['paths'], ['note.md', 'fulltext.md'])

    def test_recorded_expansion_cannot_be_changed_after_source_review(self):
        original = benchmark.ROOT
        with tempfile.TemporaryDirectory(prefix='retrieval-record-contract-') as temp:
            root = Path(temp)
            b2 = root / 'validation/golden/b2'
            freeze = benchmark.common.read_json(original / 'validation/golden/b2/freeze.json')
            for name in freeze['files']:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original / name, target)
            shutil.copytree(original / 'validation/golden/b2', b2)
            result = benchmark.check_recorded_benchmark(root)
            self.assertEqual((result['raw_passed'], result['skill_passed']), (3, 6))
            self.assertFalse(result['semantic_judgment_performed_by_checker'])
            plans_path = b2 / 'retrieval_plans.json'
            plans = benchmark.common.read_json(plans_path)
            plans['plans'][0]['expansions'][0]['query'] = 'expected-title-after-results'
            plans_path.write_text(json.dumps(plans), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'measuring inputs changed'):
                benchmark.check_recorded_benchmark(root)


if __name__ == '__main__':
    unittest.main()
