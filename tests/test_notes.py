"""Pure Note formatting fixtures; no real source material or Vault access."""
import copy
import hashlib
import html
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from researchvault import notes
from researchvault.documents import Record, read_record, write_new
from researchvault.validation import _links


class NoteRenderingTests(unittest.TestCase):
    def setUp(self):
        self.identity = {'title': 'Synthetic fin study', 'library_id': 1,
                         'zotero_key': 'FINSTUD1', 'pdf_key': 'FINPDF01',
                         'doi': '10.5555/fixture.fin', 'arxiv_id': None}
        self.options = {'note_path': '02-papers/Other/FINSTUD1.md',
                        'fulltext_path': '03-fulltext/FINSTUD1.md',
                        'pdf_path': 'D:/synthetic-originals/fin.pdf',
                        'pdf_sha256': hashlib.sha256(b'synthetic PDF bytes').hexdigest(),
                        'pages': ['Synthetic fin study.\nA trial had\t6 samples.',
                                  'Control performance was not reported.'],
                        'metadata_sources': [{'kind': 'synthetic', 'source_url': 'https://example.invalid/paper'}],
                        'synthetic': True}

    def render(self, **overrides):
        return notes.render(self.identity, **{**self.options, **overrides})

    def analysis(self):
        return {'pdf_sha256': self.options['pdf_sha256'],
                'facts': [{'statement': 'Six samples establish broad robustness.',
                           'quote': 'A trial had 6 samples.', 'page_index': 1}],
                'interpretations': ['The evidence may be too narrow for transfer.'],
                'hypotheses': ['Altered body dynamics may change the result.']}

    def test_seed_is_partial_explicit_and_pure(self):
        before = copy.deepcopy((self.identity, self.options))
        with patch.object(Path, 'open', side_effect=AssertionError('formatter must not open files')):
            result = self.render()
            again = self.render()
        self.assertEqual(result, again)
        self.assertEqual((self.identity, self.options), before)
        self.assertEqual(result['analysis_status'], 'ANALYSIS_PENDING')
        for field, expected in {'schema_version': 2, 'type': 'literature-note',
                                'status': 'draft', 'read_status': 'partial',
                                'evidence_status': 'unverified', 'human_review_status': 'pending',
                                'claim_ids': [], 'synthetic': True}.items():
            self.assertEqual(result['data'][field], expected)
        self.assertIn('### 论文源文 / Paper-source excerpts', result['body'])
        self.assertIn('### 模型分析 / Model interpretation', result['body'])
        self.assertIn('### 待验证假设 / Unverified hypotheses', result['body'])
        self.assertIn('has not visually inspected the PDF', result['body'])
        self.assertIn('No source-checked scientific excerpt', result['body'])
        self.assertNotIn('A trial had', result['body'])
        self.assertEqual(result['handoff']['pdf_sha256'], self.options['pdf_sha256'])
        expected = hashlib.sha256('\n\n'.join(self.options['pages']).encode()).hexdigest()
        self.assertEqual(result['handoff']['text_sha256'], expected)
        self.assertEqual(result['handoff']['identity'], {key: self.identity[key] for key in
                         ('library_id', 'zotero_key', 'pdf_key', 'doi', 'arxiv_id', 'title')})

    def test_canonical_template_headings_and_frontmatter_are_preserved(self):
        template = (Path(__file__).resolve().parents[1] / 'templates' / 'paper.md').read_text(encoding='utf-8')
        expected = re.findall(r'^## \d+\. .+$', template, re.M)
        result = self.render()
        self.assertEqual(re.findall(r'^## \d+\. .+$', result['body'], re.M), expected)
        from researchvault.documents import load_yaml
        template_fields = load_yaml(template.split('---', 2)[1])
        self.assertTrue(set(template_fields) <= set(result['data']))

    def test_quote_is_text_verified_but_agent_paraphrase_is_not(self):
        analysis = self.analysis()
        before = copy.deepcopy(analysis)
        result = self.render(analysis=analysis)
        self.assertEqual(analysis, before)
        self.assertEqual(result['analysis_status'], 'AGENT_ANALYSIS_CAPTURED')
        self.assertEqual(result['data']['read_status'], 'partial')
        self.assertEqual(result['data']['evidence_status'], 'unverified')
        self.assertEqual(result['data']['human_review_status'], 'pending')
        self.assertIn('E1 [fulltext_verified; text-only] Extraction page index 1: A trial had 6 samples.', html.unescape(result['body']))
        self.assertIn('agent statement [interpretation; entailment unverified]: Six samples establish broad robustness.', html.unescape(result['body']))
        self.assertIn('A1 [interpretation]', result['body'])
        self.assertIn('H1 [speculative]', result['body'])
        self.assertNotIn('[pdf_verified]', result['body'])
        self.assertIn('does not certify a statement\'s semantic entailment', result['body'])
        self.assertEqual(result['handoff']['analysis'], analysis)

    def test_changed_source_hash_or_fabricated_quote_fails_closed(self):
        changes = [('pdf_sha256', '0' * 64),
                   ('quote', 'A trial had 60 samples.'),
                   ('page_index', 2), ('page_index', 0),
                   ('page_index', True), ('page_index', 3)]
        for field, value in changes:
            analysis = self.analysis()
            if field == 'pdf_sha256':
                analysis[field] = value
            else:
                analysis['facts'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.render(analysis=analysis)

    def test_analysis_schema_does_not_accept_promoted_status_or_empty_capture(self):
        invalid = [[], {}, {'pdf_sha256': self.options['pdf_sha256']},
                   {**self.analysis(), 'read_status': 'complete'},
                   {**self.analysis(), 'facts': 'A trial had 6 samples.'},
                   {**self.analysis(), 'interpretations': [None]},
                   {**self.analysis(), 'hypotheses': [' ']},
                   {**self.analysis(), 'facts': [{'statement': 'x', 'quote': 'x', 'page_index': 1, 'label': 'pdf_verified'}]}]
        for analysis in invalid:
            with self.subTest(analysis=analysis), self.assertRaises(ValueError):
                self.render(analysis=analysis)

    def test_source_and_agent_text_cannot_inject_markdown_links_or_html(self):
        injected = '[[outside]] [click](../../secret.md) <script>fake()</script>\n## forged'
        self.identity['title'] = injected
        analysis = self.analysis()
        analysis['facts'][0]['quote'] = injected
        analysis['facts'][0]['statement'] = injected
        analysis['interpretations'] = [injected]
        analysis['hypotheses'] = [injected]
        result = self.render(analysis=analysis, pages=[injected],
                             metadata_sources=[{'source_url': injected}])
        self.assertNotIn('[[outside]]', result['body'])
        self.assertNotIn('<script>', result['body'])
        self.assertNotIn('[click](', result['body'])
        self.assertEqual(len(re.findall(r'^## \d+\. ', result['body'], re.M)), 17)
        self.assertEqual(set(re.findall(r'\[\[([^]]+)\]\]', result['body'])),
                         {self.options['fulltext_path']})
        root = Path('/synthetic-vault').resolve()
        counterpart = Record(root / self.options['fulltext_path'], self.options['fulltext_path'],
                             {'type': 'literature-fulltext'}, '')
        record = Record(root / self.options['note_path'], self.options['note_path'], result['data'], result['body'])
        self.assertEqual(_links(None, record, [record, counterpart]), [])

    def test_literal_entities_render_once_without_consuming_source_entities(self):
        samples = [r'C:\Synthetic\reader\Zotero\storage\PDFKEY01\paper_v2.pdf',
                   r'\[]()*_`#|', 'A & B < C > D "quoted" \'apostrophe\'',
                   '&#92; &amp; &#x27; &&#35;92;',
                   '中文正文 α → β; self-model ≠ body schema',
                   '[[outside]] [click](../../secret.md) <script>fake()</script>']
        for original in samples:
            with self.subTest(original=original):
                # A Markdown renderer consumes entities once. The generated
                # entity's hash must not be escaped again by a later pass.
                self.assertEqual(html.unescape(notes._literal(original)), original)
        self.assertEqual(notes._literal(r'\[]_#'), '&#92;&#91;&#93;&#95;&#35;')
        self.assertEqual(notes._literal('&#92;'), '&amp;&#35;92;')

    def test_serialized_note_preserves_source_strings_and_authored_fulltext_link(self):
        title = '身体 [schema] & "self" #1 / \'agent\''
        pdf_path = r'D:\papers\body_schema [v2]\paper.pdf'
        sources = [{'source_url': 'https://example.invalid/paper?q=a&b=c#section',
                    'captured_path': pdf_path, 'literal_entity': '&#92;',
                    'description': '中文 metadata [array] & values'}]
        self.identity['title'] = title
        result = self.render(pdf_path=pdf_path, metadata_sources=sources)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / self.options['note_path']
            write_new(path, result['data'], result['body'])
            record = read_record(path, root)
            self.assertEqual(record.data, result['data'])
            self.assertEqual(record.body, result['body'])
            self.assertEqual(record.data['pdf_path'], pdf_path)
            self.assertEqual(record.data['metadata_sources'], sources)
            body = html.unescape(record.body)
            self.assertIn('Title: ' + title + '.', body)
            self.assertIn('Original PDF source pointer: ' + pdf_path + '.', body)
            metadata_line = next(line for line in body.splitlines()
                                 if line.startswith('Metadata provenance: '))
            self.assertEqual(json.loads(metadata_line.removeprefix('Metadata provenance: ')), sources)
            self.assertEqual(set(re.findall(r'\[\[([^]]+)\]\]', record.body)),
                             {self.options['fulltext_path']})
            # Re-reading and rendering raw frontmatter inputs must not compound
            # escaping. Bodies themselves are never inputs to the formatter.
            again = notes.render(record.data, **{**self.options,
                                'pdf_path': record.data['pdf_path'],
                                'metadata_sources': record.data['metadata_sources']})
            self.assertEqual(again['body'], record.body)

    def test_literal_metadata_urls_do_not_leave_bare_autolink_triggers(self):
        sources = [{'url': 'https://arxiv.org/abs/2401.01234v2'},
                   {'url': 'www.example.invalid/paper'},
                   {'contact': 'reader@example.invalid'}]
        result = self.render(metadata_sources=sources)
        line = next(line for line in result['body'].splitlines()
                    if line.startswith('Metadata provenance: '))
        literal = line.removeprefix('Metadata provenance: ')
        self.assertEqual(json.loads(html.unescape(literal)), sources)
        # Bare GFM autolinks can swallow encoded JSON closing delimiters.
        # Full parser/DOM verification is also recorded in the quality QA.
        for trigger in ('https://', 'www.', '@'):
            self.assertNotIn(trigger, literal)
        self.assertIn('[[' + self.options['fulltext_path'] + ']]', result['body'])

    def test_source_excerpt_and_agent_text_keep_literal_punctuation_in_final_markdown(self):
        original = r'中文 [body_schema] #1: C:\robot\model & literal &#92; <control> *not emphasis*'
        analysis = {'pdf_sha256': self.options['pdf_sha256'],
                    'facts': [{'statement': original, 'quote': original, 'page_index': 1}],
                    'interpretations': [original], 'hypotheses': [original]}
        result = self.render(pages=[original], analysis=analysis)
        body = html.unescape(result['body'])
        for prefix in ('Extraction page index 1: ',
                       'agent statement [interpretation; entailment unverified]: ',
                       'A1 [interpretation]: ', 'H1 [speculative]: '):
            self.assertIn(prefix + original, body)
        self.assertNotIn('<control>', result['body'])
        self.assertNotIn('*not emphasis*', result['body'])
        self.assertEqual(result['handoff']['analysis'], analysis)

    def test_bad_paths_identity_and_source_inputs_are_rejected(self):
        invalid = [('note_path', '../escape.md'), ('fulltext_path', '/abs.md'),
                   ('fulltext_path', '03-fulltext/thing|alias.md'),
                   ('fulltext_path', '03-fulltext/x.md]]\n[[outside'),
                   ('fulltext_path', self.options['note_path']),
                   ('pdf_path', 'relative.pdf'), ('pdf_sha256', 'not-a-digest'),
                   ('pages', []), ('pages', [' ', '']), ('pages', [None]),
                   ('metadata_sources', [None]), ('metadata_sources', [{'bad': float('nan')}]),
                   ('synthetic', 1)]
        for field, value in invalid:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.render(**{field: value})
        for identity in ({**self.identity, 'pdf_key': 'FINSTUD1'},
                         {**self.identity, 'zotero_key': 'wrong'},
                         {**self.identity, 'title': None}):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                notes.render(identity, **self.options)

    def test_result_does_not_alias_mutable_source_packets(self):
        analysis = self.analysis()
        result = self.render(analysis=analysis)
        result['data']['metadata_sources'][0]['kind'] = 'modified'
        result['handoff']['analysis']['facts'][0]['quote'] = 'modified'
        result['handoff']['identity']['title'] = 'modified'
        self.assertEqual(self.options['metadata_sources'][0]['kind'], 'synthetic')
        self.assertEqual(analysis['facts'][0]['quote'], 'A trial had 6 samples.')
        self.assertEqual(self.identity['title'], 'Synthetic fin study')


if __name__ == '__main__':
    unittest.main()
