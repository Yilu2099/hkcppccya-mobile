#!/usr/bin/env python3
"""Restore public media from the existing site and verify every file's SHA-256.

Never accesses SSH credentials or private CMS data. Run before build.py in a
fresh clone. It downloads roughly 10 GB; existing verified files are skipped.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify without downloading')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'assets/bulk-manifest.json').read_text())
    missing = 0
    for row in manifest['files']:
        relative = Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe manifest path')
        target = ROOT / 'assets' / relative
        if target.is_file() and target.stat().st_size == row['bytes'] and digest(target) == row['sha256']:
            continue
        if args.check:
            missing += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        url = manifest['base_url'].rstrip('/') + '/' + quote(row['path'], safe='/')
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            try:
                with urlopen(url, timeout=60) as response:
                    for chunk in iter(lambda: response.read(1024 * 1024), b''):
                        output.write(chunk)
                output.flush()
                if temporary.stat().st_size != row['bytes'] or digest(temporary) != row['sha256']:
                    raise ValueError('Integrity check failed: ' + row['path'])
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    print(f"Verified {len(manifest['files']) - missing}/{len(manifest['files'])} public assets")
    return bool(missing)


if __name__ == '__main__':
    raise SystemExit(main())
