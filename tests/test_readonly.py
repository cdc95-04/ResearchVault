"""Read-only guarantees use only disposable files and synthetic transports."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from researchvault import acquisition, fulltext, provenance
from researchvault.cli import main
from researchvault.config import REPOSITORY, contained, load_settings, native
from researchvault.zotero import Client
from test_zotero import CANDIDATE, LocalFixture, PARENT, item


class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='researchvault-readonly-')
        self.addCleanup(self.temp.cleanup)
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop('RESEARCHVAULT_CONFIG', None)
        self.base = Path(self.temp.name).resolve()
        self.vault = self.base / 'Vault 空间'
        self.runtime = self.base / 'runtime'
        self.config = self.base / 'config.yaml'
        self.config.write_text('read_only: true\nvault_root: Vault 空间\nruntime_dir: runtime\n', encoding='utf-8')
        self.settings = load_settings(self.config)
        self.source = self.base / 'original.txt'
        self.source.write_text('Synthetic original source, 6 samples.\n', encoding='utf-8')
        self.record = {'library_id': None, 'zotero_key': 'SYNTH001', 'pdf_key': 'SYNTHPDF',
                       'doi': '10.9999/synthetic', 'title': 'Synthetic source'}

    def blocked(self, operation):
        before = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, 'read-only'):
            operation()
        after = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(self.vault.exists())
        self.assertFalse(self.runtime.exists())

    def test_readonly_blocks_init_apply_before_creating_directories(self):
        self.blocked(lambda: fulltext.initialize(self.settings, apply=True))

    def test_readonly_blocks_archive_apply_before_creating_fulltext(self):
        self.blocked(lambda: fulltext.archive(self.settings, self.record, self.source, apply=True))

    def test_readonly_blocks_ingest_apply_before_creating_fulltext(self):
        self.blocked(lambda: fulltext.ingest(self.settings, [{'record': self.record, 'source_path': str(self.source)}], apply=True))

    def test_readonly_blocks_provenance_receipt_apply(self):
        self.blocked(lambda: provenance.create_receipt(self.settings, kind='claim', object_id='synthetic',
                     source='synthetic.md', content={'claim': 'synthetic'}, apply=True))

    def test_readonly_blocks_enabled_and_disabled_acquisition(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.blocked(lambda: acquisition.run(self.settings, [], selected=[], enabled=enabled,
                             transport=lambda *a, **k: self.fail('transport reached')))

    def test_existing_previews_stay_available_without_creating_vault(self):
        self.assertFalse(fulltext.initialize(self.settings)['applied'])
        self.assertFalse(fulltext.archive(self.settings, self.record, self.source)['applied'])
        self.assertEqual(fulltext.ingest(self.settings, [{'record': self.record, 'source_path': str(self.source)}])['blocked'], 0)
        self.assertFalse(provenance.create_receipt(self.settings, kind='claim', object_id='synthetic',
                         source='synthetic.md', content={'claim': 'synthetic'})['applied'])
        self.assertFalse(self.vault.exists())
        self.assertFalse(self.runtime.exists())

    def test_config_switch_rejects_non_boolean_values(self):
        for value in ('"false"', '1', 'null', '[]', '{}'):
            self.config.write_text('vault_root: vault\nread_only: ' + value + '\n', encoding='utf-8')
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'read_only.*Boolean'):
                load_settings(self.config)

    def test_cli_and_config_switches_are_monotonic(self):
        self.assertTrue(load_settings(self.config).read_only)
        self.assertTrue(load_settings(self.config, read_only=False).read_only)
        self.config.write_text('vault_root: vault\nread_only: false\n', encoding='utf-8')
        self.assertTrue(load_settings(self.config, read_only=True).read_only)
        self.assertFalse(load_settings(self.config).read_only)
        with self.assertRaisesRegex(ValueError, 'read_only.*Boolean'):
            load_settings(self.config, read_only='false')

    def test_cli_readonly_apply_and_eval_output_are_blocked(self):
        for args in (['--config', str(self.config), 'init', '--apply'],
                     ['--read-only', '--vault', str(self.vault), 'init', '--apply'],
                     ['--read-only', 'eval-run', 'unused.json', 'unused.json', '--output', str(self.vault / 'report.json')],
                     ['--config', str(self.config), 'eval-run', 'unused.json', 'unused.json', '--output', str(self.vault / 'report.json')]):
            output, errors = io.StringIO(), io.StringIO()
            with self.subTest(args=args), redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(main(args), 2)
                self.assertIn('read-only', json.loads(errors.getvalue())['error'])
            self.assertFalse(self.vault.exists())

    def test_cli_passes_readonly_to_zotero_client(self):
        with patch('researchvault.zotero.Client') as constructor, redirect_stdout(io.StringIO()):
            constructor.return_value.inventory.return_value = {'complete': True}
            self.assertEqual(main(['--config', str(self.config), 'zotero-inventory']), 0)
        self.assertTrue(constructor.call_args.kwargs['read_only'])


class ReadOnlyZoteroTests(unittest.TestCase):
    def client(self, fixture):
        return Client('users/0', transport=fixture, read_only=True)

    def test_non_get_and_mutation_marked_get_never_reach_transport(self):
        fixture = LocalFixture()
        client = self.client(fixture)
        for method, kwargs in [('POST', {}), ('PUT', {}), ('DELETE', {}), ('PATCH', {}),
                               ('GET', {'mutation': True}), ('GET', {'upload': True})]:
            with self.subTest(method=method, kwargs=kwargs), self.assertRaisesRegex(ValueError, 'read-only'):
                client._request(method, client._url('/items'), **kwargs)
        self.assertEqual(fixture.calls, [])

    def test_create_apply_blocks_before_any_request_or_receipt(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'ZOTERO_API_KEY': 'synthetic-test-key'}):
            root = Path(temporary)
            fixture = LocalFixture()
            with self.assertRaisesRegex(ValueError, 'read-only'):
                self.client(fixture).create_item(PARENT, apply=True, receipt_path=root / 'receipt' / 'intent.jsonl')
            self.assertEqual(fixture.calls, [])
            self.assertEqual(list(root.iterdir()), [])

    def test_import_apply_blocks_before_source_read_or_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = LocalFixture([item('PARENT01', PARENT)])
            with self.assertRaisesRegex(ValueError, 'read-only'):
                self.client(fixture).import_pdf('PARENT01', root / 'absent.pdf', CANDIDATE,
                                                apply=True, receipt_path=root / 'receipt.jsonl')
            self.assertEqual(fixture.calls, [])
            self.assertEqual(list(root.iterdir()), [])

    def test_internal_receipt_and_mutation_routes_cannot_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = LocalFixture()
            client = self.client(fixture)
            with self.assertRaisesRegex(ValueError, 'read-only'):
                client._receipt(root / 'receipt.jsonl', 'synthetic', {}, None)
            receipt = unittest.mock.Mock()
            with self.assertRaisesRegex(ValueError, 'read-only'):
                client._mutate(receipt, 'synthetic', client._url('/items'), b'[]', {})
            receipt.event.assert_not_called()
            self.assertEqual(fixture.calls, [])
            self.assertEqual(list(root.iterdir()), [])

    def test_zotero_preview_stays_readonly(self):
        fixture = LocalFixture()
        self.assertEqual(self.client(fixture).create_item(PARENT)['status'], 'PLANNED')
        self.assertTrue(fixture.calls)
        self.assertEqual({call[0] for call in fixture.calls}, {'GET'})

    def test_explicit_client_flag_is_strict(self):
        self.assertTrue(Client('users/0', read_only=True).read_only)
        for value in ('false', 0, 1, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'read_only.*Boolean'):
                Client('users/0', read_only=value)


class ValidationOutputTests(unittest.TestCase):
    def test_validation_workspace_must_be_isolated_and_explicit(self):
        from researchvault.safety import validation_output
        for root in ('', REPOSITORY, Path(tempfile.gettempdir()), Path.home() / 'not-a-validation-workspace'):
            with self.subTest(root=root), self.assertRaises(ValueError):
                validation_output(root, 'report.json')

    def test_device_namespace_spellings_are_rejected_before_resolution(self):
        for value in ('\\\\?\\C:\\synthetic', '//?/C:/synthetic', '\\\\.\\C:\\synthetic', '//./C:/synthetic'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'namespace'):
                native(value, Path.cwd())

    def test_spaces_cjk_and_protected_overlap(self):
        from researchvault.safety import validation_output
        with tempfile.TemporaryDirectory(prefix='researchvault-paths-') as temporary:
            base = Path(temporary).resolve()
            workspace, vault = base / 'validation 空间', base / 'vault'
            relative = 'nested 空间/report.json'
            target = validation_output(workspace, relative, protected_roots=[vault])
            self.assertTrue(target.is_relative_to(workspace))
            self.assertFalse(workspace.exists())
            target.parent.mkdir(parents=True)
            target.write_text('{}', encoding='utf-8')
            self.assertEqual(target.read_text(encoding='utf-8'), '{}')
            for forbidden in (vault, vault / 'output', base):
                with self.subTest(root=forbidden), self.assertRaises(ValueError):
                    validation_output(forbidden, 'report.json', protected_roots=[vault])
            for name in ('../escape.json', 'C:/escape.json', '/escape.json'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validation_output(workspace, name, protected_roots=[vault])

    def test_long_path_resolution_and_host_filesystem_capability(self):
        from researchvault.safety import validation_output
        with tempfile.TemporaryDirectory(prefix='researchvault-paths-') as temporary:
            workspace = Path(temporary).resolve() / 'validation 空间'
            relative = '/'.join(['long segment 汉字 ' + 'x' * 45] * 5) + '/report.json'
            target = validation_output(workspace, relative)
            self.assertTrue(target.is_relative_to(workspace))
            self.assertGreater(len(str(target)), 260)
            try:
                target.parent.mkdir(parents=True)
                target.write_text('{}', encoding='utf-8')
            except OSError as exc:
                if os.name == 'nt' and getattr(exc, 'winerror', None) in {3, 206}:
                    self.skipTest('Host Windows long-path I/O is unavailable; containment resolution passed, POSIX CI covers I/O')
                raise
            self.assertEqual(target.read_text(encoding='utf-8'), '{}')

    def test_symlink_escape_is_rejected_before_creation(self):
        from researchvault.safety import validation_output
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workspace, vault = base / 'workspace', base / 'vault'
            workspace.mkdir(); vault.mkdir()
            try:
                (workspace / 'jump').symlink_to(vault, target_is_directory=True)
            except OSError:
                self.skipTest('Host does not permit symlink creation; CI POSIX jobs cover it')
            with self.assertRaises(ValueError):
                validation_output(workspace, 'jump/report.json', protected_roots=[vault])
            self.assertFalse((vault / 'report.json').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction semantics are covered by Windows CI')
    def test_windows_junction_escape_is_rejected_before_creation(self):
        from researchvault.safety import validation_output
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workspace, vault = base / 'workspace', base / 'vault'
            workspace.mkdir(); vault.mkdir()
            junction = workspace / 'jump'
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(vault)], capture_output=True)
            if result.returncode:
                self.skipTest('Host does not permit directory junction creation')
            try:
                with self.assertRaises(ValueError):
                    validation_output(workspace, 'jump/report.json', protected_roots=[vault])
                with self.assertRaises(ValueError):
                    contained(workspace, 'jump/report.json')
                self.assertFalse((vault / 'report.json').exists())
            finally:
                junction.rmdir()


if __name__ == '__main__':
    unittest.main()
