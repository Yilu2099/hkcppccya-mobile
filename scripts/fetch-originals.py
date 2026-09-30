"""Archive exact public image bytes; resumable and independently verifiable."""
import argparse, hashlib, json, pathlib, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch(key, source, root):
    parts = urllib.parse.urlsplit(source)
    ext = pathlib.PurePosixPath(parts.path).suffix.lower()
    path = root / (key + ext)
    url = urllib.parse.urlunsplit((parts.scheme, parts.netloc,
        urllib.parse.quote(urllib.parse.unquote(parts.path), safe='/'), parts.query, ''))
    if not path.exists():
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = response.read()
                if not data.startswith((b'\xff\xd8', b'\x89PNG')):
                    raise ValueError('Source is not a JPEG or PNG image')
                tmp = path.with_suffix('.tmp'); tmp.write_bytes(data); tmp.replace(path)
                break
            except Exception:
                if attempt == 2: raise
                time.sleep(1)
    data = path.read_bytes()
    return {'key': key, 'file': path.name, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('sources'); p.add_argument('destination')
    args = p.parse_args(); root = pathlib.Path(args.destination); root.mkdir(parents=True, exist_ok=True)
    sources = json.loads(pathlib.Path(args.sources).read_text()); rows = []; failed = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(fetch, key, url, root): key for key, url in sources.items()}
        for i, job in enumerate(as_completed(jobs), 1):
            try: rows.append(job.result())
            except Exception as e: failed.append({'key': jobs[job], 'error': str(e)})
            if i % 100 == 0: print(i, '/', len(sources), 'failed', len(failed), flush=True)
    report = {'images': sorted(rows, key=lambda x: x['key']), 'failed': failed}
    (root.parent / 'legacy-source-report.json').write_text(json.dumps(report, indent=2))
    print('Archived', len(rows), 'images;', sum(r['bytes'] for r in rows), 'bytes;', len(failed), 'failures', flush=True)
    if failed: raise SystemExit(1)
