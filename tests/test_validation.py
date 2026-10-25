"""Source extraction keeps its bytes without becoming authored Markdown."""
from pathlib import Path
import tempfile
import unittest

from researchvault.config import load_settings
from researchvault.documents import read_record, write_new
from researchvault.fulltext import archive
from researchvault.validation import validate


class FulltextBodyBoundary(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.settings = load_settings(vault=self.base / 'vault', synthetic=True, cwd=self.base)
        self.source = self.base / 'original.txt'
        self.source_bytes = b'Original equation [w](x), and source citation [[1]].\n'
        self.source.write_bytes(self.source_bytes)
        self.note_path = '02-papers/Other/source.md'
        metadata = {'zotero_key': 'LINKSRC1', 'pdf_key': 'LINKPDF1', 'library_id': None,
                    'title': 'Synthetic extracted source', 'doi': '10.5555/fixture.link'}
        result = archive(self.settings, metadata, self.source, note_path=self.note_path, apply=True)
        self.fulltext = self.settings.resolve(result['path'])
        self.note = self.settings.resolve(self.note_path)
        write_new(self.note, {**metadata, 'schema_version': 2, 'type': 'literature-note',
                             'read_status': 'partial', 'evidence_status': 'unverified',
                             'fulltext_path': result['path']}, 'Partial source interpretation.\n')

    def test_original_fulltext_math_and_citations_are_not_vault_links(self):
        before = self.fulltext.read_bytes()
        report = validate(self.settings)
        self.assertTrue(report['valid'], report)
        self.assertNotIn('BROKEN_LINK', {row['code'] for row in report['diagnostics']})
        self.assertEqual(self.fulltext.read_bytes(), before)
        self.assertEqual(read_record(self.fulltext, self.settings.vault).body.encode('utf-8'), self.source_bytes)

    def test_authored_note_still_rejects_the_same_broken_markdown_link(self):
        with self.note.open('a', encoding='utf-8') as stream:
            stream.write('An authored link [w](x).\n')
        report = validate(self.settings)
        self.assertFalse(report['valid'])
        broken = [row for row in report['diagnostics'] if row['code'] == 'BROKEN_LINK']
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0]['path'], self.note_path)

    def test_fulltext_source_and_text_digest_checks_remain_enforced(self):
        original_archive = self.fulltext.read_bytes()
        for changed, expected in (('source', 'SOURCE_DRIFT'), ('text', 'FULLTEXT_DRIFT')):
            with self.subTest(changed=changed):
                self.source.write_bytes(self.source_bytes)
                self.fulltext.write_bytes(original_archive)
                if changed == 'source':
                    self.source.write_bytes(self.source_bytes + b'Changed original source.\n')
                else:
                    self.fulltext.write_bytes(original_archive + b'Changed extraction.\n')
                report = validate(self.settings)
                self.assertFalse(report['valid'])
                self.assertIn(expected, {row['code'] for row in report['diagnostics']})

    def test_fulltext_attachment_identity_checks_remain_enforced(self):
        content = self.fulltext.read_text(encoding='utf-8')
        self.fulltext.write_text(content.replace('pdf_key: LINKPDF1', 'pdf_key: OTHER001'), encoding='utf-8')
        report = validate(self.settings)
        self.assertFalse(report['valid'])
        self.assertIn('SOURCE_MISMATCH', {row['code'] for row in report['diagnostics']})

    def test_fulltext_reciprocal_frontmatter_links_remain_enforced(self):
        content = self.note.read_text(encoding='utf-8')
        self.note.write_text(content.replace('03-fulltext/LINKSRC1.md', '03-fulltext/missing.md'), encoding='utf-8')
        report = validate(self.settings)
        self.assertFalse(report['valid'])
        self.assertIn('RECIPROCAL_LINK', {row['code'] for row in report['diagnostics']})


if __name__ == '__main__':
    unittest.main()
