"""The environment inspector observes temporary source data without modifying it."""
from pathlib import Path
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.validate_environment import inspect


class EnvironmentHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.zotero = self.base / 'source library'
        self.vault = self.base / '研究 notes'
        self.zotero.mkdir(); self.vault.mkdir()
        con = sqlite3.connect(self.zotero / 'zotero.sqlite')
        con.executescript('''
          CREATE TABLE items(itemID INTEGER,key TEXT,libraryID INTEGER,itemTypeID INTEGER);
          CREATE TABLE itemTypes(itemTypeID INTEGER,typeName TEXT);
          CREATE TABLE itemData(itemID INTEGER,fieldID INTEGER,valueID INTEGER);
          CREATE TABLE fields(fieldID INTEGER,fieldName TEXT);
          CREATE TABLE itemDataValues(valueID INTEGER,value TEXT);
          CREATE TABLE itemCreators(itemID INTEGER,creatorID INTEGER,orderIndex INTEGER);
          CREATE TABLE creators(creatorID INTEGER,firstName TEXT,lastName TEXT);
          CREATE TABLE itemAttachments(itemID INTEGER,parentItemID INTEGER,linkMode INTEGER,contentType TEXT,path TEXT);
          CREATE TABLE collectionItems(itemID INTEGER,collectionID INTEGER);
          INSERT INTO itemTypes VALUES(1,'journalArticle');
          INSERT INTO items VALUES(1,'FAKEKEY1',1,1);
          INSERT INTO fields VALUES(1,'title');
          INSERT INTO itemDataValues VALUES(1,'Synthetic 机器人');
          INSERT INTO itemData VALUES(1,1,1);
          INSERT INTO creators VALUES(1,'Fictional','Researcher');
          INSERT INTO itemCreators VALUES(1,1,0);
          INSERT INTO collectionItems VALUES(1,1);
        ''')
        con.commit(); con.close()
        folder = self.vault / 'nested'; folder.mkdir()
        (folder / 'FAKEKEY1.md').write_text('---\nschema_version: 2\n---\n[[another]] [link](file.md)', encoding='utf-8')

    def test_readonly_counts_and_private_outputs_are_separated(self):
        original = (self.zotero / 'zotero.sqlite').read_bytes()
        report, run = inspect(self.zotero, self.vault, self.base / 'scratch')
        self.assertEqual(report['zotero']['parent_items'], 1)
        self.assertEqual(report['zotero']['without_pdf'], 1)
        self.assertEqual(report['obsidian']['nested_markdown'], 1)
        self.assertTrue(report['source_files_unchanged'])
        self.assertEqual(original, (self.zotero / 'zotero.sqlite').read_bytes())
        self.assertNotIn('Synthetic', json.dumps(report))
        self.assertNotIn(str(self.base), json.dumps(report))
        self.assertTrue((self.base / 'scratch' / run / 'inventory.private.json').exists())
        self.assertFalse((self.vault / 'inventory.private.json').exists())

    def test_workspace_inside_protected_source_fails_before_creation(self):
        for source in (self.zotero, self.vault):
            workspace = source / 'output'
            with self.subTest(source=source), patch('scripts.validate_environment.fingerprint') as fingerprint, \
                    patch('scripts.validate_environment.inventory_files') as inventory:
                with self.assertRaisesRegex(ValueError, 'protected data root'):
                    inspect(self.zotero, self.vault, workspace)
                fingerprint.assert_not_called()
                inventory.assert_not_called()
                self.assertFalse(workspace.exists())

    def test_empty_explicit_roots_fail_before_source_reads(self):
        selected = (self.zotero, self.vault, self.base / 'scratch')
        for index in range(3):
            roots = list(selected)
            roots[index] = ''
            with self.subTest(index=index), patch('scripts.validate_environment.fingerprint') as fingerprint, \
                    patch('scripts.validate_environment.inventory_files') as inventory:
                with self.assertRaisesRegex(ValueError, 'Explicit filesystem root'):
                    inspect(*roots)
                fingerprint.assert_not_called()
                inventory.assert_not_called()
                self.assertFalse((self.base / 'scratch').exists())

    def test_cli_requires_selected_zotero_root_before_inspection(self):
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'validate_environment.py'
        workspace = self.base / 'scratch'
        result = subprocess.run([sys.executable, str(script), '--vault', str(self.vault),
                                 '--workspace', str(workspace)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--zotero-data', result.stderr)
        self.assertFalse(workspace.exists())


if __name__ == '__main__':
    unittest.main()
