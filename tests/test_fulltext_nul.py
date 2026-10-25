"""Source-mapped NUL preservation; synthetic fonts, never real-paper fixtures."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from researchvault.config import load_settings
from researchvault.documents import read_record
from researchvault.fulltext import archive


def mapped_pdf(path, unicode_hex):
    """A nonzero text code has an explicit source-owned Unicode mapping."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    cmap = DecodedStreamObject()
    cmap.set_data(('''/CIDInit /ProcSet findresource begin
12 dict begin begincmap
/CIDSystemInfo << /Registry (Fixture) /Ordering (Unicode) /Supplement 0 >> def
/CMapName /Fixture def /CMapType 2 def
1 begincodespacerange <00> <FF> endcodespacerange
1 beginbfchar <21> <''' + unicode_hex + '''> endbfchar
endcmap CMapName currentdict /CMap defineresource pop end end
''').encode('ascii'))
    font = DictionaryObject({NameObject('/Type'):NameObject('/Font'),
                             NameObject('/Subtype'):NameObject('/Type1'),
                             NameObject('/BaseFont'):NameObject('/Helvetica'),
                             NameObject('/Encoding'):NameObject('/WinAnsiEncoding'),
                             NameObject('/ToUnicode'):writer._add_object(cmap)})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
        DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    content = DecodedStreamObject()
    content.set_data(b'BT /F1 12 Tf 20 100 Td (A!B) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(content)
    writer.write(path)


class SourceMappedNulTests(unittest.TestCase):
    def test_explicit_zero_unicode_mapping_is_preserved_through_archive_and_reread(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            source = base/'mapped.pdf'
            mapped_pdf(source, '0000')
            original = source.read_bytes()
            page = PdfReader(source, strict=True).pages[0]
            # The source text operand is nonzero; its Unicode mapping introduces NUL.
            self.assertIn(b'(A!B)', page.get_contents().get_data())
            self.assertNotIn(b'\x00', page.get_contents().get_data())
            extracted = page.extract_text()
            self.assertEqual(extracted, 'A\x00B')
            settings = load_settings(vault=base/'vault', synthetic=True, cwd=base)
            identity = {'library_id':None, 'zotero_key':'NULPAP01',
                        'pdf_key':'NULPDF01', 'title':'Synthetic Unicode mapping',
                        'doi':'10.5555/synthetic.nul'}
            result = archive(settings, identity, source, method='pdf', apply=True)
            record = read_record(settings.resolve(result['path']), settings.vault)
            self.assertEqual(record.body, extracted)
            self.assertEqual(record.body.encode('utf-8'), b'A\x00B')
            self.assertEqual(record.data['source_sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(record.data['text_sha256'], hashlib.sha256(b'A\x00B').hexdigest())
            self.assertNotEqual(record.data['text_sha256'], hashlib.sha256(b'AB').hexdigest())
            before = record.path.read_bytes()
            self.assertTrue(archive(settings, identity, source, method='pdf', apply=True)['reused'])
            self.assertEqual(record.path.read_bytes(), before)
            self.assertEqual(source.read_bytes(), original)

    def test_same_text_operand_with_printable_unicode_mapping_does_not_gain_nul(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'printable.pdf'
            mapped_pdf(source, '0021')
            page = PdfReader(source, strict=True).pages[0]
            self.assertIn(b'(A!B)', page.get_contents().get_data())
            self.assertEqual(page.extract_text(), 'A!B')
            self.assertNotIn('\x00', page.extract_text())


if __name__ == '__main__':
    unittest.main()
