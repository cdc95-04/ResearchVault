"""Golden harness failure accounting uses only disposable synthetic inputs."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import validate_golden as golden


class GoldenHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='researchvault-golden-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'inputs'
        self.papers = self.base / 'papers'
        for directory in (self.root / 'annotations', self.root / 'captures', self.papers):
            directory.mkdir(parents=True)
        names = patch.dict(golden.PDF_NAMES, {'synthetic': 'synthetic.pdf'}, clear=True)
        names.start()
        self.addCleanup(names.stop)
        self.annotation = {
            'paper_id': 'synthetic', 'pdf_sha256': 'a' * 64,
            'review': {'human_reviewed': False, 'implementation_outputs_seen': False},
            'claims': [{'id': 'synthetic-c1', 'numeric_facts': [
                {'value': 0.72, 'unit': 'success_fraction', 'condition': 'Synthetic condition A'}]}],
            'retrieval_queries': []}
        self.capture = {
            'paper_id': 'synthetic', 'human_reviewed': False, 'golden_seen_before_capture': False,
            'claims': [{'id': 'synthetic-c1', 'numbers': [
                {'name': 'condition-a-success', 'value': 0.72}]}]}
        self.comparison = {'records': [{'paper_id': 'synthetic', 'claim_id': 'synthetic-c1',
            'numeric_mappings': [{'golden_index': 0, 'capture_name': 'condition-a-success',
                                  'mapping_reason': 'Same synthetic condition and success-fraction unit.'}]}]}
        self.save_inputs()

    def save_inputs(self):
        for path, data in ((self.root / 'annotations' / 'synthetic.json', self.annotation),
                           (self.root / 'captures' / 'synthetic.json', self.capture)):
            path.write_text(json.dumps(data), encoding='utf-8')
        self.comparison['input_manifest'] = [{'paper_id': 'synthetic',
            'annotation_sha256': golden.fingerprint(self.root / 'annotations' / 'synthetic.json'),
            'capture_sha256': golden.fingerprint(self.root / 'captures' / 'synthetic.json')}]
        (self.root / 'comparison.json').write_text(json.dumps(self.comparison), encoding='utf-8')

    def test_json_reader_rejects_duplicate_keys_and_nonfinite_values(self):
        path = self.base / 'invalid.json'
        for document in ('{"value": 1, "value": 2}', '{"nested": {"x": 1, "x": 2}}',
                         '{"value": NaN}', '{"value": Infinity}', '{"value": -Infinity}',
                         '{"value": 1e999}'):
            with self.subTest(document=document):
                path.write_text(document, encoding='utf-8')
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    golden.read_json(path)
                self.assertEqual(path.read_bytes(), before)

    def test_wrong_capture_number_remains_a_failed_measurement_and_exit(self):
        annotations, captures = golden.inputs(self.root)
        valid = golden.compare_numbers(annotations, captures, self.comparison)
        self.assertEqual((valid['matched'], valid['total']), (1, 1))
        captures['synthetic']['claims'][0]['numbers'][0]['value'] = 0.27
        measured = golden.compare_numbers(annotations, captures, self.comparison)
        self.assertEqual((measured['matched'], measured['total']), (0, 1))
        self.assertFalse(measured['checks'][0]['passed'])
        output = io.StringIO()
        with patch.object(golden, 'inputs', return_value=(annotations, captures)), \
             patch.object(golden, 'reviewed_comparison', return_value=self.comparison), \
             patch('sys.argv', ['validate_golden', '--check-inputs']), redirect_stdout(output):
            self.assertEqual(golden.main(), 1)
        report = json.loads(output.getvalue())
        self.assertFalse(report['human_reviewed'])
        self.assertFalse(report['pdf_integration_executed'])
        self.assertEqual(report['numeric_consistency']['matched'], 0)

    def test_missing_or_duplicate_numeric_and_claim_mappings_are_rejected(self):
        annotations, captures = golden.inputs(self.root)
        for mutation in ('missing-number', 'duplicate-number', 'missing-claim', 'duplicate-claim'):
            changed = copy.deepcopy(self.comparison)
            row = changed['records'][0]
            if mutation == 'missing-number':
                row['numeric_mappings'].clear()
            elif mutation == 'duplicate-number':
                row['numeric_mappings'].append(copy.deepcopy(row['numeric_mappings'][0]))
            elif mutation == 'missing-claim':
                changed['records'].clear()
            else:
                changed['records'].append(copy.deepcopy(row))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                golden.compare_numbers(annotations, captures, changed)

    def test_pending_human_review_is_preserved_and_false_approval_rejected(self):
        annotations, captures = golden.inputs(self.root)
        self.assertIs(annotations['synthetic']['review']['human_reviewed'], False)
        self.assertIs(captures['synthetic']['human_reviewed'], False)
        for source in ('annotation', 'capture'):
            self.annotation['review']['human_reviewed'] = source == 'annotation'
            self.capture['human_reviewed'] = source == 'capture'
            self.save_inputs()
            before = {p: p.read_bytes() for p in self.root.rglob('*.json')}
            with self.subTest(source=source), self.assertRaises(ValueError):
                golden.inputs(self.root)
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_claim_identity_cannot_escape_the_temporary_claim_directory(self):
        dangerous = '../../outside-claim'
        self.annotation['claims'][0]['id'] = dangerous
        self.capture['claims'][0]['id'] = dangerous
        self.annotation['retrieval_queries'] = [{'query': 'synthetic question', 'expected_claim_ids': [dangerous]}]
        self.save_inputs()
        with self.assertRaises(ValueError):
            golden.inputs(self.root)

    def test_run_uses_explicit_temporary_configuration_despite_environment(self):
        foreign = self.base / 'unrelated-config.yaml'
        foreign.write_text('schema_version: 999\n', encoding='utf-8')
        (self.papers / 'synthetic.pdf').write_bytes(b'%PDF-synthetic-digest-check')
        with patch.dict(os.environ, {'RESEARCHVAULT_CONFIG': str(foreign)}), \
             patch.object(golden, 'load_settings', wraps=golden.load_settings) as load:
            with self.assertRaises(ValueError):
                golden.run(self.papers, root=self.root)
        self.assertGreaterEqual(load.call_count, 1)
        for call in load.call_args_list:
            config = call.kwargs.get('config_path')
            self.assertIsNotNone(config, 'An unrelated environment config must not influence the validation workspace')
            self.assertNotEqual(Path(config).resolve(), foreign.resolve())
            self.assertTrue(Path(config).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))

    def successful_report_except_numbers(self):
        return {'baseline': {'valid': True}, 'restored_baseline_valid': True,
                'retrieval_relevant_papers_found': 1, 'retrieval_query_count': 1,
                'injected_errors_detected': 1, 'injected_error_count': 1,
                'numeric_consistency': {'matched': 0, 'total': 1, 'checks': [{'passed': False}]},
                'human_reviewed': False}

    def test_full_run_cli_cannot_pass_when_numeric_consistency_fails(self):
        with patch.object(golden, 'run', return_value=self.successful_report_except_numbers()), \
             patch('sys.argv', ['validate_golden', '--papers-dir', str(self.papers)]), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(golden.main(), 1)

    def test_existing_report_error_withholds_private_path_and_preserves_file(self):
        output = self.base / 'private-output-directory'
        output.mkdir()
        target = output / 'golden-report.json'
        target.write_bytes(b'Existing report must remain unchanged.\n')
        before = target.read_bytes()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(golden, 'run', return_value=self.successful_report_except_numbers()), \
             patch('sys.argv', ['validate_golden', '--papers-dir', str(self.papers), '--output-workspace', str(output)]), \
             redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(golden.main(), 2)
        self.assertEqual(target.read_bytes(), before)
        rendered = stdout.getvalue() + stderr.getvalue()
        self.assertIn('FileExistsError', rendered)
        self.assertNotIn(str(self.base), rendered)
        self.assertNotIn(json.dumps(str(self.base))[1:-1], rendered)

    def test_wrong_pdf_digest_rejects_before_parsing_and_preserves_all_inputs(self):
        source = self.papers / 'synthetic.pdf'
        source.write_bytes(b'%PDF-synthetic-invalid-bytes-for-digest-check-only')
        before = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        with patch.object(golden.fulltext, 'archive', side_effect=AssertionError('PDF parsed before digest validation')) as archive:
            with self.assertRaisesRegex(ValueError, 'PDF digest differs'):
                golden.run(self.papers, root=self.root)
            archive.assert_not_called()
        after = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_changed_capture_cannot_reuse_an_old_semantic_comparison(self):
        self.assertEqual(golden.reviewed_comparison(self.root), self.comparison)
        source = self.root / 'captures' / 'synthetic.json'
        changed = copy.deepcopy(self.capture)
        changed['claims'][0]['statement'] = 'An unreviewed assertion with unchanged numbers.'
        source.write_text(json.dumps(changed), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'reviewed input'):
            golden.reviewed_comparison(self.root)


if __name__ == '__main__':
    unittest.main()
