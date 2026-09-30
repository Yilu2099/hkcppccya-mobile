"""Verify every archived original against the source byte hash before publishing."""
import argparse, hashlib, json, pathlib
from concurrent.futures import ThreadPoolExecutor

p = argparse.ArgumentParser(); p.add_argument('manifest'); p.add_argument('root'); args = p.parse_args()
root = pathlib.Path(args.root).resolve()
manifest = json.loads(pathlib.Path(args.manifest).read_text())
records = {v['original']: v['sha256'] for v in manifest.values()}
def check(row):
    name, expected = row; path = (root/name).resolve()
    if root not in path.parents or not path.is_file(): return name
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): digest.update(chunk)
    return name if digest.hexdigest()!=expected else None
with ThreadPoolExecutor(max_workers=4) as pool:
    failed = [name for name in pool.map(check, records.items()) if name]
print(json.dumps({'originals':len(records),'verified':len(records)-len(failed),'failed':failed},ensure_ascii=False),flush=True)
if failed: raise SystemExit(1)
