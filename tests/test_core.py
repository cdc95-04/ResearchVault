"""Independent behavioral cases use fresh temporary data, never a real library."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from researchvault.config import REPOSITORY, contained, load_settings, native
from researchvault.documents import load_yaml, read_record, write_new
from researchvault.identity import select, check_records


class ExplicitStorage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop('RESEARCHVAULT_CONFIG', None)

    def config(self, content):
        file = self.base / 'settings.yaml'
        file.write_text(content, encoding='utf-8')
        return file

    def test_missing_root_never_creates_personal_data(self):
        with self.assertRaises(ValueError):
            load_settings(cwd=self.base)
        self.assertEqual(list(self.base.iterdir()), [])

    def test_explicit_root_and_config_relative_resolution(self):
        settings = load_settings(self.config('vault_root: notes\n'), cwd=self.base)
        self.assertEqual(settings.vault, self.base / 'notes')
        self.assertFalse(settings.vault.exists())
        self.assertEqual(load_settings(vault='selected', cwd=self.base).vault, self.base / 'selected')

    def test_explicit_config_wins_over_bad_environment(self):
        os.environ['RESEARCHVAULT_CONFIG'] = str(self.base / 'missing.yaml')
        with self.assertRaises(ValueError):
            load_settings(vault=self.base / 'data')
        self.assertEqual(load_settings(self.config('vault_root: notes\n')).vault, self.base / 'notes')

    def test_code_checkout_requires_explicit_synthetic_location(self):
        for path, synthetic in ((REPOSITORY / 'private', False), (REPOSITORY / 'private', True), (REPOSITORY / 'examples' / 'demo', False)):
            with self.subTest(path=path, synthetic=synthetic), self.assertRaises(ValueError):
                load_settings(vault=path, synthetic=synthetic, cwd=self.base)
        self.assertTrue(load_settings(vault=REPOSITORY / 'examples' / 'demo', synthetic=True, cwd=self.base).options['synthetic'])

    def test_overlapping_roots_paths_and_folder_categories_fail(self):
        for text in ('vault_root: data\nruntime_dir: data/downloads\n',
                     'vault_root: data\npaths: {papers: shared, fulltext: shared/sub}\n',
                     'vault_root: data\nfolders: {research: [A, A/B]}\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                load_settings(self.config(text))

    def test_malformed_settings_and_secret_values_rejected(self):
        for text in ('vault_root: data\nschema_version: 0\n', 'vault_root: data\nsynthetic: yesplease\n',
                     'vault_root: data\npaths: []\n', 'vault_root: data\nzotero: {library_id: true}\n',
                     'vault_root: data\nzotero: {api_key: private}\n', 'vault_root: data\nacquisition: {enabled: enabled}\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                load_settings(self.config(text))

    def test_traversal_and_absolute_record_paths_fail(self):
        for path in ('../escape', '/absolute', 'A/../../escape', 'A//B', '.', 'C:relative', 'C:/absolute'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                contained(self.base, path)
        self.assertEqual(contained(self.base, 'A\\B'), self.base / 'A' / 'B')

    def test_foreign_absolute_roots_are_not_reinterpreted(self):
        value = '/home/synthetic/research' if os.name == 'nt' else 'C:/Synthetic/Research'
        with self.assertRaises(ValueError):
            native(value, self.base)

    def test_symlink_cannot_escape_selected_root(self):
        inside, outside = self.base / 'inside', self.base / 'outside'
        inside.mkdir(); outside.mkdir()
        try:
            (inside / 'jump').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Host has no symlink creation privilege')
        with self.assertRaises(ValueError):
            contained(inside, 'jump/secret.txt')

    def test_yaml_duplicate_keys_are_not_silently_overwritten(self):
        for text in ('a: 1\na: 2', 'root:\n  a: 1\n  a: 2', '? [a,b]\n: bad'):
            with self.assertRaises(ValueError):
                load_yaml(text)

    def test_original_body_and_no_overwrite(self):
        path = self.base / 'source.md'
        path.write_bytes(b'---\r\ntype: literature-fulltext\r\n---\r\nOriginal  spacing.\r\n')
        self.assertEqual(read_record(path, self.base).body, 'Original  spacing.\r\n')
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            write_new(path, {'type': 'literature-note'}, 'overwrite')
        self.assertEqual(before, path.read_bytes())


class NamespacedIdentity(unittest.TestCase):
    def setUp(self):
        self.record = {'library_id': None, 'zotero_key': 'RIVER001', 'pdf_key': 'RIVER002',
                       'title': 'Synthetic study of a flexible link', 'doi': '10.5555/synthetic.link'}

    def test_explicit_key_never_falls_back(self):
        with self.assertRaises(ValueError):
            select([self.record], zotero_key='MISSING1', publication_doi=self.record['doi'])

    def test_key_checks_additional_identifiers(self):
        with self.assertRaises(ValueError):
            select([self.record], zotero_key='RIVER001', publication_doi='10.5555/conflicting')

    def test_title_is_only_a_unique_lookup_hint(self):
        second = {**self.record, 'zotero_key': 'OTHER001', 'pdf_key': 'OTHER002', 'doi': None}
        with self.assertRaises(ValueError):
            select([self.record, second], name=self.record['title'])
        self.assertEqual(select([self.record], name='  Synthetic study of a flexible link ')['zotero_key'], 'RIVER001')

    def test_library_namespace_is_not_ignored(self):
        group = {**self.record, 'library_id': 42}
        self.assertEqual(select([self.record, group], zotero_key='RIVER001', library_id=42)['library_id'], 42)
        with self.assertRaises(ValueError):
            select([self.record], zotero_key='RIVER001', library_id=42)

    def test_attachment_selection_is_explicit(self):
        other = {**self.record, 'pdf_key': 'RIVER003'}
        with self.assertRaises(ValueError):
            select([self.record, other], zotero_key='RIVER001')
        self.assertEqual(select([self.record, other], zotero_key='RIVER001', pdf_key='RIVER003')['pdf_key'], 'RIVER003')
        self.assertEqual(select([self.record], pdf_key='RIVER002')['zotero_key'], 'RIVER001')

    def test_arxiv_versions_are_not_merged_and_missing_fields_cannot_erase_conflicts(self):
        preprint = {**self.record, 'arxiv_id': '2501.12345v2'}
        self.assertEqual(select([preprint], arxiv_id='https://arxiv.org/abs/2501.12345v2')['zotero_key'], 'RIVER001')
        with self.assertRaises(ValueError):
            select([preprint], zotero_key='RIVER001', arxiv_id='2501.12345v1')
        with self.assertRaises(ValueError):
            check_records([self.record, {**self.record, 'doi': None, 'title': None}, {**self.record, 'doi': '10.5555/contradiction'}])
        with self.assertRaises(ValueError):
            check_records([{**self.record, 'doi': 'not-an-identifier'}])

    def test_collisions_are_detected_before_selection(self):
        for changed in ({'zotero_key': 'OTHER001'}, {'pdf_key': 'RIVER001'}, {'doi': '10.5555/different'},
                        {'library_id': True}, {'zotero_key': 'title-derived'}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                check_records([self.record, {**self.record, **changed}])


if __name__ == '__main__':
    unittest.main()
