"""The public identifier command defaults to a side-effect-free preview."""
from contextlib import redirect_stdout, redirect_stderr
import io
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from researchvault.cli import main, parser
try:
    from tests import test_identifier_intake as fixtures
except ModuleNotFoundError:
    import test_identifier_intake as fixtures


class IdentifierCLI(unittest.TestCase):
    def call(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(list(args))
        return status, json.loads(output.getvalue() or errors.getvalue())

    def test_default_and_explicit_preview_do_not_call_network_or_create_roots(self):
        for flags in ((), ('--dry-run',)):
            with tempfile.TemporaryDirectory() as directory:
                vault = Path(directory) / 'uncreated-vault'
                with patch('researchvault.resolution.resolve', side_effect=AssertionError('network')), \
                        patch('researchvault.zotero.Client.inventory', side_effect=AssertionError('Zotero read')):
                    status, result = self.call('--vault', str(vault), 'intake', 'doi:10.9999/example', *flags)
                self.assertEqual(status, 0)
                self.assertEqual(result['status'], 'PREVIEW')
                self.assertFalse(vault.exists())
                self.assertFalse(result['items'][0]['network_reads'])

    def test_read_only_apply_fails_before_metadata_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('researchvault.resolution.resolve', side_effect=AssertionError('network')):
            status, result = self.call('--vault', str(Path(directory) / 'vault'), '--read-only',
                                       'intake', '2401.01234v2', '--apply', '--enable', '--allow-zotero-create')
            self.assertEqual(status, 2)
            self.assertIn('read-only', result['error'])
            self.assertFalse((Path(directory) / 'vault').exists())

    def test_partial_batch_exits_nonzero_and_redacts_invalid_secret_input(self):
        secret = 'DO_NOT_PRINT_THIS_SECRET'
        with tempfile.TemporaryDirectory() as directory:
            status, result = self.call('--vault', str(Path(directory) / 'vault'), 'intake',
                                       '2401.01234v2', 'https://example.org/a?token=' + secret)
        self.assertEqual(status, 1)
        self.assertEqual(result['blocked'], 1)
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result['items'][0]['status'], 'PLANNED')

    def test_apply_and_dry_run_are_mutually_exclusive(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
            parser().parse_args(['intake', '2401.01234v2', '--apply', '--dry-run'])
        self.assertEqual(stopped.exception.code, 2)


@unittest.skipUnless(importlib.util.find_spec('pypdf'), 'Optional pypdf required')
class IdentifierCLIEndToEnd(unittest.TestCase):
    setUp = fixtures.IdentifierIntakeTests.setUp

    def test_public_cli_apply_validate_and_resume_use_real_adapters_without_duplicate_writes(self):
        arguments = ['--config', str(self.base / 'config.json'), 'intake', fixtures.DOI,
                     '--apply', '--enable', '--allow-zotero-create', '--email', 'synthetic@example.org']

        def call(args):
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                code = main(args)
            return code, json.loads(output.getvalue() or errors.getvalue())

        def normalizing_local(method, url, **kwargs):
            response = self.local(method, url, **kwargs)
            # Real API read-back includes an empty firstName for two-field names.
            # An unstructured full author must use the documented `name` form.
            for item in self.local.items:
                for creator in item['data'].get('creators', []):
                    if 'lastName' in creator:
                        creator.setdefault('firstName', '')
            return response

        with patch('researchvault.discovery.public_request', side_effect=self.public), \
                patch('researchvault.zotero.local_request', side_effect=normalizing_local), \
                patch('researchvault.intake.time.sleep'):
            status, first = call(arguments)
            self.assertEqual(status, 0, first)
            self.assertEqual(first['items'][0]['status'], 'ARCHIVED_ANALYSIS_PENDING')
            self.assertEqual(first['counts']['parent_created'], 1)
            self.assertEqual(first['counts']['attachment_created'], 1)
            self.assertTrue(first['items'][0]['zotero_read_back_verified'])
            self.assertEqual(self.local.items[0]['data']['creators'],
                             [{'creatorType': 'author', 'name': fixtures.AUTHOR}])
            status, validated = call(['--config', str(self.base / 'config.json'), 'validate'])
            self.assertEqual(status, 0, validated)
            self.assertTrue(validated['valid'])
            self.assertEqual((validated['records'], validated['errors']), (2, 0))
            posts = sum(request[0] == 'POST' for request in self.local.calls)
            public_reads = len(self.public.calls)
            status, resumed = call([*arguments, '--resume'])
            self.assertEqual(status, 0, resumed)
            self.assertEqual(resumed['counts']['parent_created'], 0)
            self.assertEqual(resumed['counts']['attachment_created'], 0)
            self.assertEqual(sum(request[0] == 'POST' for request in self.local.calls), posts)
            self.assertEqual(len(self.public.calls), public_reads)
