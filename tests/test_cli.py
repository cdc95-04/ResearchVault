"""Command boundaries exercise previews and read-only failure reporting."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from researchvault.cli import main
from researchvault.documents import read_record


class Commands(unittest.TestCase):
    def call(self, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(list(arguments))
        return status, json.loads(output.getvalue() or errors.getvalue())

    def test_missing_root_is_an_actionable_error(self):
        status, result = self.call('validate')
        self.assertEqual(status, 2)
        self.assertIn('--vault', result['error'])

    def test_fixture_validation_reports_expected_partial_states(self):
        source = Path(__file__).resolve().parents[1] / 'examples' / 'synthetic.yaml'
        status, result = self.call('--config', str(source), 'validate')
        self.assertEqual(status, 0)
        self.assertEqual((result['errors'], result['warnings'], result['records']), (0, 6, 6))

    def test_init_preview_and_missing_vault_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'new-vault'
            status, result = self.call('--vault', str(root), 'init')
            self.assertEqual(status, 0)
            self.assertFalse(root.exists())
            self.assertFalse(result['applied'])
            status, result = self.call('--vault', str(root), 'validate')
            self.assertEqual(status, 1)
            self.assertFalse(result['valid'])

    def test_help_identifies_ingest_as_selected_batch_source_archive(self):
        for arguments in (['--help'], ['ingest', '--help']):
            with self.subTest(arguments=arguments):
                output = io.StringIO()
                with redirect_stdout(output), self.assertRaises(SystemExit) as stopped:
                    main(arguments)
                self.assertEqual(stopped.exception.code, 0)
                text = ' '.join(output.getvalue().split())
                self.assertIn('Selected batch source archive', text)
                if arguments[0] == 'ingest':
                    self.assertIn('Does not generate Paper Notes or analysis.', text)

    def test_ingest_preserves_preview_apply_reuse_and_blocked_results(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            vault = base / 'synthetic-vault'
            source = base / 'source.txt'
            source.write_bytes(b'Synthetic CLI source.\r\nA trial had 4 samples.\r\n')
            note_path = '02-papers/Other/cli-source.md'
            batch = base / 'batch.json'
            batch.write_text(json.dumps([
                {'record': {'zotero_key': 'CLIBAT01', 'pdf_key': 'CLIPDF01', 'library_id': None,
                            'title': 'Synthetic CLI source'},
                 'source_path': str(source), 'note_path': note_path},
                {'record': {}},
            ]), encoding='utf-8')
            arguments = ('--vault', str(vault), '--synthetic', 'ingest', str(batch))

            status, preview = self.call(*arguments)
            self.assertEqual(status, 1)
            self.assertEqual(set(preview), {'applied', 'items', 'blocked'})
            self.assertFalse(preview['applied'])
            self.assertEqual([row['status'] for row in preview['items']], ['planned', 'blocked'])
            self.assertEqual(preview['blocked'], 1)
            self.assertFalse(vault.exists())

            status, applied = self.call(*arguments, '--apply')
            self.assertEqual(status, 1)
            self.assertTrue(applied['applied'])
            self.assertEqual([row['status'] for row in applied['items']], ['archived', 'blocked'])
            self.assertEqual(applied['blocked'], 1)
            archived = vault / applied['items'][0]['path']
            saved = read_record(archived, vault)
            self.assertEqual(saved.type, 'literature-fulltext')
            self.assertEqual(saved.body.encode('utf-8'), source.read_bytes())
            self.assertEqual(list(vault.rglob('*.md')), [archived])
            self.assertFalse((vault / note_path).exists())

            before = archived.read_bytes()
            status, reused = self.call(*arguments, '--apply')
            self.assertEqual(status, 1)
            self.assertEqual([row['status'] for row in reused['items']], ['reused', 'blocked'])
            self.assertFalse(reused['items'][0]['applied'])
            self.assertTrue(reused['items'][0]['reused'])
            self.assertEqual(archived.read_bytes(), before)

    def zotero_inputs(self, base, *, runtime=True):
        configuration = {'schema_version': 2, 'vault_root': str(base / 'vault')}
        if runtime:
            configuration['runtime_dir'] = str(base / 'runtime')
        config = base / 'config.json'
        config.write_text(json.dumps(configuration), encoding='utf-8')
        metadata = base / 'parent.json'
        metadata.write_text(json.dumps({'itemType': 'journalArticle', 'title': 'Selected paper'}), encoding='utf-8')
        return config, metadata

    def test_zotero_create_receipt_is_inside_runtime_instead_of_vault(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            config, metadata = self.zotero_inputs(base)
            with patch('researchvault.zotero.Client') as client:
                client.return_value.create_item.return_value = {'status': 'CREATED'}
                status, result = self.call('--config', str(config), 'zotero-create', str(metadata),
                                           '--apply', '--receipt', 'receipts/selected-parent.jsonl')
            self.assertEqual(status, 0, result)
            client.return_value.create_item.assert_called_once_with(
                {'itemType': 'journalArticle', 'title': 'Selected paper'}, apply=True,
                receipt_path=base / 'runtime' / 'receipts' / 'selected-parent.jsonl')
            self.assertFalse((base / 'vault').exists())

    def test_zotero_receipt_rejects_missing_runtime_absolute_and_traversal_before_api_access(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            for command in ('zotero-create', 'zotero-import'):
                for runtime, receipt, error in (
                    (False, 'receipts/item.jsonl', 'runtime_dir'),
                    (True, str(base / 'outside.jsonl'), 'relative'),
                    (True, '../outside.jsonl', 'traversal'),
                    (True, None, '--receipt'),
                ):
                    with self.subTest(command=command, runtime=runtime, receipt=receipt):
                        config, metadata = self.zotero_inputs(base, runtime=runtime)
                        arguments = ['--config', str(config), command, str(metadata)]
                        if command == 'zotero-import':
                            arguments.extend(['PARENT01', str(base / 'unused.pdf')])
                        arguments.append('--apply')
                        if receipt is not None:
                            arguments.extend(['--receipt', receipt])
                        with patch('researchvault.zotero.Client') as client:
                            status, result = self.call(*arguments)
                            client.assert_not_called()
                        self.assertEqual(status, 2, result)
                        self.assertIn(error, result['error'])

    def test_zotero_receipt_rejects_link_escape_before_api_access(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            config, metadata = self.zotero_inputs(base)
            runtime, outside = base / 'runtime', base / 'outside'
            runtime.mkdir()
            outside.mkdir()
            try:
                (runtime / 'receipts').symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                if os.name != 'nt':
                    self.skipTest('Directory symlinks are unavailable: ' + str(exc))
                # Windows junctions exercise real link resolution without requiring
                # the administrator privilege needed for directory symlinks.
                linked = subprocess.run(['cmd', '/c', 'mklink', '/J',
                                         str(runtime / 'receipts'), str(outside)],
                                        capture_output=True)
                if linked.returncode:
                    self.skipTest('Directory symlinks and junctions are unavailable')
            with patch('researchvault.zotero.Client') as client:
                status, result = self.call('--config', str(config), 'zotero-create', str(metadata),
                                           '--apply', '--receipt', 'receipts/item.jsonl')
                client.assert_not_called()
            self.assertEqual(status, 2, result)
            self.assertIn('escapes', result['error'])


if __name__ == '__main__':
    unittest.main()
