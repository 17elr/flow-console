"""Read existing S3 objects into a new overlay directory; never PUT, DELETE or edit originals."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3

def recover(client, bucket, records, available, output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'downloaded': [], 'unavailable': [], 'already_available': 0, 'remote_writes': 0}
    seen = set()
    for row in records:
        key, expected = row.get('storage_key'), row.get('sha256')
        if not key or not expected or expected in available or key in seen:
            report['already_available'] += 1
            continue
        seen.add(key)
        target = (output / key).resolve()
        if not target.is_relative_to(output) or ':' in key or '\\' in key:
            raise ValueError('Object key escapes recovery directory')
        try:
            response = client.get_object(Bucket=bucket, Key=key)
            try: raw = response['Body'].read(30 * 1024 * 1024 + 1)
            finally: response['Body'].close()
            if len(raw) > 30 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError('Remote object hash or size mismatch')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream: stream.write(raw)
            available.add(expected)
            report['downloaded'].append({'key': key, 'sha256': expected, 'size': len(raw)})
        except Exception as exc:
            report['unavailable'].append({'key': key, 'error_type': type(exc).__name__})
    with output.with_name(output.name+'-report.json').open('x',encoding='utf-8') as stream: json.dump(report,stream,ensure_ascii=False,indent=2)
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True); parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--env-file', type=Path, action='append', default=[])
    args = parser.parse_args()
    from dotenv import dotenv_values
    import boto3
    from botocore.config import Config
    config = {}
    for path in args.env_file: config.update(dotenv_values(path))
    config.update(os.environ)
    if not all(config.get(k) for k in ['S3_BUCKET','S3_ACCESS_KEY','S3_SECRET_KEY']): raise ValueError('Existing S3 read credentials are not configured')
    client = boto3.client('s3', endpoint_url=config.get('S3_ENDPOINT_URL'), aws_access_key_id=config['S3_ACCESS_KEY'], aws_secret_access_key=config['S3_SECRET_KEY'], region_name=config.get('S3_REGION','us-east-1'), config=Config(connect_timeout=10,read_timeout=15,retries={'max_attempts':1},s3={'addressing_style':'virtual'}))
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    available = {item['sha256'] for item in manifest['files']}
    records = []
    with closing(sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        for table in ['assets','asset_versions','packaging_presets']:
            records.extend(dict(row) for row in db.execute('SELECT storage_key,sha256 FROM '+table))
    result = recover(client, config['S3_BUCKET'], records, available, args.output)
    print(json.dumps({'downloaded':len(result['downloaded']),'unavailable':len(result['unavailable']),'remote_writes':0}))
