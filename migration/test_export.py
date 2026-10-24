import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

spec = importlib.util.spec_from_file_location('export_legacy', Path(__file__).with_name('export_legacy.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ExportTest(unittest.TestCase):
    def test_readonly_snapshot_values_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / 'source.db'
            with closing(sqlite3.connect(database)) as conn:
                conn.execute('CREATE TABLE products(id INTEGER PRIMARY KEY, price REAL, secret TEXT)')
                conn.execute('INSERT INTO products VALUES(7,9.9,?)', ('must-not-export',))
                conn.commit()
            before = module.sha(database)
            assets = root / 'assets'; assets.mkdir(); (assets / 'original.png').write_bytes(b'original')
            summary = module.export(database, root / 'export', {'assets': assets})
            self.assertEqual(before, module.sha(database))
            self.assertEqual(1, summary['rows'])
            row = json.loads((root / 'export/products.jsonl').read_text())
            self.assertEqual('9.9', row['price'])
            self.assertEqual('[REDACTED]', row['secret'])
            manifest = json.loads((root / 'export/manifest.json').read_text())
            self.assertEqual(module.sha(assets / 'original.png'), manifest['files'][0]['sha256'])
            with self.assertRaises(FileExistsError): module.export(database, root / 'export', {})

if __name__ == '__main__': unittest.main()
