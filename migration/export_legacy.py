"""Read-only SQLite snapshot and content-addressed asset inventory. Never edits source data."""
import argparse
import hashlib
import json
import math
import shutil
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path

MONEY = {'price', 'cost', 'weight_g', 'price_multiplier'}

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def scrub(value):
    if isinstance(value, dict):
        return {key: '[REDACTED]' if any(word in key.lower().replace('_', '').replace('-', '') for word in ('password', 'secret', 'token', 'credential', 'apikey', 'appkey', 'authorization', 'cookie', 'signature')) or key.lower() in {'sign', 'x-sign'} else scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str) and value.lstrip().startswith(('{', '[')):
        try:
            return json.dumps(scrub(json.loads(value)), ensure_ascii=False, sort_keys=True)
        except (ValueError, TypeError):
            pass
    if isinstance(value, bytes):
        raise ValueError('BLOB columns require an explicit mapping; export stopped without changing source')
    return value

def export(database, target, roots, extra_assets=()):
    database, target = database.resolve(strict=True), target.resolve()
    if target == database.parent or database.is_relative_to(target):
        raise ValueError('Export must use a new directory outside the source database directory')
    sources = list(roots.items()) + [('assets', root) for root in extra_assets]
    for _, root in sources:
        if target.is_relative_to(root.resolve()):
            raise ValueError('Export cannot be placed inside a source asset directory')
    target.mkdir(parents=True, exist_ok=False)
    manifest = {'format': 'flow-legacy-v1', 'tables': {}, 'files': [], 'precision_differences': [], 'foreign_key_issues': [], 'secrets': 'redacted in JSONL; SQLite backup is private'}
    uri = database.as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as source:
        source.row_factory = sqlite3.Row
        source.execute('BEGIN')
        with closing(sqlite3.connect(target / 'private-snapshot.db')) as snapshot:
            source.backup(snapshot)
        manifest['foreign_key_issues'] = [list(row) for row in source.execute('PRAGMA foreign_key_check')]
        names = [row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for table in names:
            if not table.replace('_', '').isalnum():
                raise ValueError('Unsupported table identifier')
            output = target / (table + '.jsonl')
            count = 0
            with output.open('w', encoding='utf-8', newline='\n') as stream:
                for row in source.execute('SELECT * FROM "' + table + '" ORDER BY rowid'):
                    record = dict(row)
                    for key, value in record.items():
                        if key in MONEY and isinstance(value, (int, float)):
                            if isinstance(value, float) and not math.isfinite(value):
                                raise ValueError(f'Non-finite amount: {table} {record.get("id")} {key}')
                            record[key] = str(Decimal(str(value)))
                            if isinstance(value, float) and Decimal.from_float(value) != Decimal(str(value)):
                                manifest['precision_differences'].append({'table': table, 'id': record.get('id'), 'field': key, 'decimal_string': record[key], 'sqlite_binary_exact': str(Decimal.from_float(value)), 'action': 'no rounding applied'})
                    stream.write(json.dumps(scrub(record), ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
                    count += 1
            manifest['tables'][table] = {'rows': count, 'sha256': sha(output), 'foreign_keys': [list(row) for row in source.execute('PRAGMA foreign_key_list("' + table + '")')]}
    for kind, root in sources:
        root = root.resolve(strict=True)
        for file in sorted(root.rglob('*')):
            if not file.is_file() or file.is_symlink():
                continue
            real = file.resolve(strict=True)
            if not real.is_relative_to(root):
                raise ValueError('Asset escapes source root')
            relative = Path(kind) / file.relative_to(root)
            destination = target / 'files' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if sha(destination) != sha(file):
                    raise ValueError('Conflicting asset overlay; nothing is overwritten')
                continue
            with file.open('rb') as source, destination.open('xb') as output:
                shutil.copyfileobj(source, output)
            digest = sha(file)
            if sha(destination) != digest:
                raise ValueError('Source asset changed during copy; retain this export for diagnosis and retry in a new directory')
            manifest['files'].append({'path': relative.as_posix(), 'size': file.stat().st_size, 'sha256': digest})
    manifest['private_snapshot_sha256'] = sha(target / 'private-snapshot.db')
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'tables': len(manifest['tables']), 'rows': sum(item['rows'] for item in manifest['tables'].values()), 'files': len(manifest['files']), 'foreign_key_issues': len(manifest['foreign_key_issues']), 'precision_differences': len(manifest['precision_differences'])}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--compliance', type=Path)
    parser.add_argument('--extra-assets', type=Path, action='append', default=[])
    args = parser.parse_args()
    roots = {kind: path for kind, path in {'assets': args.assets, 'compliance': args.compliance}.items() if path and path.exists()}
    print(json.dumps(export(args.database, args.output, roots, args.extra_assets), ensure_ascii=False))
