"""Package release metadata and supported configuration use synthetic inputs."""
from importlib import metadata, reload
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

import researchvault
from researchvault.config import DEFAULTS, configured_read_only, load_settings
from researchvault.discovery import Response, get


class PackageVersion(unittest.TestCase):
    def test_runtime_release_matches_installed_distribution(self):
        self.assertEqual(researchvault.__version__, metadata.version('researchvault'))

    def test_metadata_release_changes_independently_of_record_schema(self):
        try:
            with patch('importlib.metadata.version', return_value='9.8.7') as version:
                reload(researchvault)
                version.assert_called_once_with('researchvault')
                self.assertEqual(researchvault.__version__, '9.8.7')
                self.assertEqual(researchvault.SCHEMA_VERSION, 2)
                self.assertEqual(DEFAULTS['schema_version'], 2)
        finally:
            reload(researchvault)

    def test_discovery_request_identifies_the_package_release(self):
        requests = []

        def transport(method, url, **options):
            requests.append((method, url, options))
            return Response(200, {}, b'{}')

        with patch('researchvault.discovery.__version__', '9.8.7'):
            response, url = get('https://example.org/metadata', transport=transport)
        self.assertEqual(response.body, b'{}')
        self.assertEqual(url, 'https://example.org/metadata')
        self.assertEqual(requests, [('GET', url, {
            'headers': {'User-Agent': 'ResearchVault/9.8.7', 'Accept': 'application/json, application/pdf'},
            'body': None, 'max_bytes': 4_000_000,
        })])


class RemovedConfigurationFields(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop('RESEARCHVAULT_CONFIG', None)

    def config(self, text):
        source = self.base / 'settings.yaml'
        source.write_text('vault_root: synthetic-notes\n' + text, encoding='utf-8')
        return source

    def test_removed_fields_fail_even_with_null_values(self):
        for text, field in (
            ('project_version: 0.1.0\n', 'project_version'),
            ('project_version: null\n', 'project_version'),
            ('language: zh-CN\n', 'language'),
            ('language: null\n', 'language'),
            ('zotero: {data_dir: synthetic-library}\n', 'zotero.data_dir'),
            ('zotero: {data_dir: null}\n', 'zotero.data_dir'),
        ):
            source = self.config(text)
            with self.subTest(field=field, text=text):
                for reader in (load_settings, configured_read_only):
                    with self.assertRaisesRegex(ValueError, field.replace('.', r'\.')):
                        reader(source, cwd=self.base)
        self.assertFalse((self.base / 'synthetic-notes').exists())

    def test_defaults_and_shipped_configs_use_only_supported_fields(self):
        self.assertNotIn('project_version', DEFAULTS)
        self.assertNotIn('language', DEFAULTS)
        self.assertNotIn('data_dir', DEFAULTS['zotero'])
        repository = Path(__file__).resolve().parents[1]
        settings = load_settings(repository / 'config' / 'default.yaml', vault=self.base / 'synthetic-notes')
        self.assertEqual(settings.options['schema_version'], 2)
        synthetic = load_settings(repository / 'examples' / 'synthetic.yaml')
        self.assertEqual(synthetic.options['schema_version'], 2)
        self.assertTrue(synthetic.options['synthetic'])

    def test_unrelated_extension_keys_retain_existing_configuration_policy(self):
        settings = load_settings(self.config('extension: {enabled: true}\nzotero: {extension_hint: synthetic}\n'))
        self.assertEqual(settings.options['extension'], {'enabled': True})
        self.assertEqual(settings.options['zotero']['extension_hint'], 'synthetic')


if __name__ == '__main__':
    unittest.main()
