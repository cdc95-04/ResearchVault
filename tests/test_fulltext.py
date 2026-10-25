"""Fresh synthetic archive and retrieval cases; no upstream fixture text."""
from pathlib import Path
import tempfile
import unittest
import yaml

from researchvault.config import load_settings
from researchvault.documents import read_record, write_new
from researchvault import fulltext
from researchvault.validation import validate, verify_claim


class SourceWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.settings = load_settings(vault=self.base / 'vault', synthetic=True, cwd=self.base)
        self.source = self.base / 'original.txt'
        self.source.write_bytes(b'Synthetic elastic fin.\r\nA trial had 6 samples.\r\n')
        self.meta = {'zotero_key': 'FINSTUD1', 'pdf_key': 'FINPDF01', 'library_id': None,
                     'title': 'Synthetic fin study', 'doi': '10.5555/fixture.fin'}
        self.note_path = '02-papers/Other/fin.md'

    def archive(self, **kwargs):
        return fulltext.archive(self.settings, self.meta, self.source, note_path=self.note_path, **kwargs)

    def note(self, **extra):
        path = self.settings.resolve(self.note_path)
        metadata = {**self.meta, 'schema_version': 2, 'type': 'literature-note', 'read_status': 'partial',
                    'evidence_status': 'unverified', 'fulltext_path': '03-fulltext/FINSTUD1.md', **extra}
        write_new(path, metadata, 'An interpretation of the elastic fin.\n')
        return read_record(path, self.settings.vault)

    def test_init_is_preview_then_create_only(self):
        plan = fulltext.initialize(self.settings)
        self.assertFalse(self.settings.vault.exists())
        self.assertEqual(len(plan['templates']), 22)
        fulltext.initialize(self.settings, apply=True)
        target = self.settings.folder('templates') / 'paper.md'
        target.write_text('User custom template', encoding='utf-8')
        fulltext.initialize(self.settings, apply=True)
        self.assertEqual(target.read_text(), 'User custom template')

    def test_archive_preserves_original_and_does_not_create_analysis(self):
        plan = self.archive()
        self.assertFalse(self.settings.vault.exists())
        self.archive(apply=True)
        saved = read_record(self.settings.resolve(plan['path']), self.settings.vault)
        self.assertEqual(saved.body.encode('utf-8'), self.source.read_bytes())
        self.assertFalse(self.settings.resolve(self.note_path).exists())
        self.assertTrue(self.archive(apply=True)['reused'])

    def test_archive_refuses_conflicting_existing_source(self):
        first = self.archive(apply=True)
        saved = self.settings.resolve(first['path']).read_bytes()
        self.source.write_text('Altered source', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.archive(apply=True)
        self.assertEqual(saved, self.settings.resolve(first['path']).read_bytes())
        self.assertIn('SOURCE_DRIFT', {d['code'] for d in validate(self.settings)['diagnostics']})

    def test_identity_mismatch_blocks_before_writing(self):
        self.note()
        self.meta['doi'] = '10.5555/another.fin'
        with self.assertRaises(ValueError):
            self.archive(apply=True)
        self.assertFalse(self.settings.folder('fulltext').exists())

    def test_wrong_verification_parent_never_falls_back(self):
        result = self.archive(apply=True)
        note = self.note()
        text = read_record(self.settings.resolve(result['path']), self.settings.vault)
        claim = {'source_notes': [note.relative], 'evidence_status': 'fulltext_verified',
                 'verification': [{'fulltext_path': text.relative, 'zotero_key': 'OTHER001', 'quote': 'A trial had 6 samples.'}]}
        self.assertIn('SOURCE_MISMATCH', {d['code'] for d in verify_claim(self.settings, claim, [note, text])})

    def test_knowledge_hit_does_not_hide_empty_note_recall(self):
        self.archive(apply=True)
        write_new(self.settings.resolve('01-knowledge/Concepts/fin.md'),
                  {'schema_version': 2, 'type': 'knowledge-concept', 'evidence_status': 'unverified'}, 'elastic fin')
        result = fulltext.retrieve(self.settings, 'elastic fin')
        self.assertIn('literature-fulltext', result['layers'])
        self.assertEqual(result['record_count'], 2)

    def test_malformed_batch_item_does_not_abort_later_selection(self):
        result = fulltext.ingest(self.settings, [{'record': None, 'source_path': str(self.source)},
                                                {'record': self.meta, 'source_path': str(self.source)}])
        self.assertEqual([r['status'] for r in result['items']], ['blocked', 'planned'])

    def test_partial_is_warning_but_completed_missing_pdf_is_error(self):
        self.archive(apply=True)
        note = self.note()
        report = validate(self.settings)
        self.assertTrue(report['valid'], report)
        text = note.path.read_text(encoding='utf-8').replace('read_status: partial', 'read_status: complete')
        note.path.write_text(text, encoding='utf-8')
        self.assertFalse(validate(self.settings)['valid'])

    def test_partial_fulltext_verified_does_not_claim_pdf_verification(self):
        self.archive(apply=True)
        self.note(evidence_status='fulltext_verified')
        report = validate(self.settings)
        self.assertTrue(report['valid'], report)
        self.assertEqual(report['warnings'], 2)

    def test_original_excerpt_required_and_wrong_attachment_rejected(self):
        result = self.archive(apply=True)
        note = self.note()
        text = read_record(self.settings.resolve(result['path']), self.settings.vault)
        claim = {'source_notes': [note.relative], 'evidence_status': 'fulltext_verified',
                 'verification': [{'fulltext_path': text.relative, 'pdf_key': 'FINPDF01', 'quote': 'A trial had 6 samples.'}]}
        self.assertEqual(verify_claim(self.settings, claim, [note, text]), [])
        claim['verification'][0]['quote'] = 'A trial had 60 samples.'
        self.assertIn('FABRICATED_QUOTE', {i['code'] for i in verify_claim(self.settings, claim, [note, text])})
        claim['verification'][0]['pdf_key'] = 'OTHER001'
        self.assertIn('SOURCE_MISMATCH', {i['code'] for i in verify_claim(self.settings, claim, [note, text])})

    def test_important_note_claim_requires_sidecar_and_every_source_resolves(self):
        self.archive(apply=True)
        note = self.note(claim_ids=['fin-important'])
        self.assertIn('CLAIM_MISSING', {d['code'] for d in validate(self.settings)['diagnostics']})
        claim = {'source_notes': [note.relative, 'nonexistent.md'], 'evidence_status': 'derived'}
        self.assertIn('SOURCE_MISMATCH', {d['code'] for d in verify_claim(self.settings, claim, [note])})

    def test_actual_pdf_page_bounds_and_invalid_pdf(self):
        from pypdf import PdfWriter
        pdf = self.base / 'synthetic.pdf'
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
        writer.write(pdf)
        result = self.archive(apply=True)
        note = self.note(pdf_path=str(pdf))
        text = read_record(self.settings.resolve(result['path']), self.settings.vault)
        claim = {'source_notes': [note.relative], 'evidence_status': 'pdf_verified',
                 'verification': [{'fulltext_path': text.relative, 'locator': {'pdf_page': 2}}]}
        self.assertIn('FABRICATED_PAGE', {i['code'] for i in verify_claim(self.settings, claim, [note, text])})
        pdf.write_bytes(b'broken synthetic bytes')
        self.assertIn('PDF_UNCHECKED', {i['code'] for i in verify_claim(self.settings, claim, [note, text])})

    def test_reciprocal_links_counts_and_link_errors(self):
        result = self.archive(apply=True)
        self.note()
        data = {'schema_version': 2, 'type': 'knowledge-concept', 'evidence_status': 'note_supported',
                'source_notes': [self.note_path, self.note_path], 'source_papers': ['FINSTUD1'], 'evidence_count': 2}
        path = self.settings.resolve('01-knowledge/Concepts/fin.md')
        write_new(path, data, 'See [[missing-source]].')
        codes = {d['code'] for d in validate(self.settings)['diagnostics']}
        self.assertTrue({'EVIDENCE_COUNT', 'BROKEN_LINK'} <= codes)
        archive_path = self.settings.resolve(result['path'])
        archive_path.write_text(archive_path.read_text(encoding='utf-8').replace(self.note_path, 'absent.md'), encoding='utf-8')
        self.assertIn('RECIPROCAL_LINK', {d['code'] for d in validate(self.settings)['diagnostics']})

    def test_local_recall_has_real_counts_and_explicit_layers(self):
        self.archive(apply=True); self.note()
        result = fulltext.retrieve(self.settings, 'elastic fin')
        self.assertEqual(result['paper_count'], 1)
        self.assertNotIn('literature-fulltext', result['layers'])
        result = fulltext.retrieve(self.settings, '6 samples')
        self.assertEqual(result['paper_count'], 1)
        self.assertIn('literature-fulltext', result['layers'])
        result = fulltext.retrieve(self.settings, 'elastic fin', supplementary=True)
        self.assertEqual((result['record_count'], result['paper_count']), (2, 1))

    def test_ingest_is_selected_serial_and_keeps_blocked_item(self):
        result = fulltext.ingest(self.settings, [{'record': self.meta, 'source_path': str(self.source)}, {'record': {}}], apply=True)
        self.assertEqual([r['status'] for r in result['items']], ['archived', 'blocked'])
        self.assertEqual(result['blocked'], 1)

    def test_diff_and_migration_never_modify_records(self):
        note = self.note()
        before = note.path.read_bytes()
        proposed = self.base / 'proposal.md'; proposed.write_text('A proposed change', encoding='utf-8')
        self.assertIn('+A proposed change', fulltext.diff(self.settings, note.relative, proposed)['diff'])
        self.assertFalse(fulltext.migration(self.settings)['applied'])
        self.assertEqual(before, note.path.read_bytes())


if __name__ == '__main__':
    unittest.main()
