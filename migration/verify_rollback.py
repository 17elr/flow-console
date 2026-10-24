"""Validate that the preserved SQLite snapshot and copied files can be read without source writes."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            value.update(chunk)
    return value.hexdigest()

def verify(source, export, roots, extras=()):
    manifest = json.loads((export / 'manifest.json').read_text(encoding='utf-8'))
    checked_rows = 0
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as original, closing(sqlite3.connect((export / 'private-snapshot.db').resolve().as_uri() + '?mode=ro', uri=True)) as snapshot:
        original.execute('BEGIN'); snapshot.execute('BEGIN')
        for table, metadata in manifest['tables'].items():
            assert table.replace('_', '').isalnum(), 'invalid identifier'
            before = original.execute('SELECT * FROM "' + table + '" ORDER BY rowid').fetchall()
            restored = snapshot.execute('SELECT * FROM "' + table + '" ORDER BY rowid').fetchall()
            assert before == restored, f'Source changed since backup: {table}'
            assert len(restored) == metadata['rows'], f'Backup row count mismatch: {table}'
            checked_rows += len(restored)
        assert not snapshot.execute('PRAGMA foreign_key_check').fetchall(), 'Backup foreign keys failed'
    assert digest(export / 'private-snapshot.db') == manifest['private_snapshot_sha256'], 'Backup changed'
    for item in manifest['files']:
        relative = Path(item['path'])
        root = roots[relative.parts[0]].resolve()
        source_file = root.joinpath(*relative.parts[1:]).resolve()
        assert source_file.is_relative_to(root), 'Source file escaped root'
        if not source_file.exists() and relative.parts[0] == 'assets':
            for overlay in extras:
                candidate = overlay.resolve().joinpath(*relative.parts[1:]).resolve()
                assert candidate.is_relative_to(overlay.resolve()), 'Overlay escaped root'
                if candidate.exists(): source_file = candidate; break
        assert digest(source_file) == digest(export / 'files' / relative) == item['sha256'], 'Asset changed'
    return {'status': 'PASSED', 'scope': 'read-only snapshot restoration check; no production cutover', 'tables': len(manifest['tables']), 'rows': checked_rows, 'files': len(manifest['files']), 'source_writes': 0, 'external_calls': 0}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True); parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True); parser.add_argument('--compliance', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--extra-assets', type=Path, action='append', default=[])
    args = parser.parse_args()
    roots = {'assets': args.assets, 'compliance': args.compliance}
    report = verify(args.database, args.export, roots, args.extra_assets)
    with args.report.open('x', encoding='utf-8') as stream: json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report))
