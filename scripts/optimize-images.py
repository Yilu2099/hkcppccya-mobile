"""Build responsive WebP images while keeping supplied/source bytes untouched."""
import base64, hashlib, io, json, pathlib, time, urllib.parse, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageOps

root = pathlib.Path(__file__).resolve().parents[1]; assets = root/'assets'
web = assets/'web'; web.mkdir(exist_ok=True)
originals = assets/'originals'; originals.mkdir(exist_ok=True)
news = json.loads((assets/'news.json').read_text())
gallery = json.loads((assets/'gallery.json').read_text())
covers = {a['cover'] for a in news+gallery if a.get('cover')}
scans = {p for a in news if a['category']=='media' for p in a.get('images', [])}
jobs = []
sources = json.loads((assets/'image-sources.json').read_text())
for key, url in sources.items():
    ext = pathlib.PurePosixPath(urllib.parse.urlsplit(url).path).suffix.lower()
    jobs.append(('legacy/'+key+'.webp', originals/'legacy'/(key+ext), 'scan' if 'legacy/'+key+'.webp' in scans else 'photo'))

def preserve(key, data, suffix, kind='photo'):
    path = originals/'supplied'/(hashlib.sha256(data).hexdigest()[:24]+suffix.lower())
    path.parent.mkdir(exist_ok=True)
    if not path.exists(): path.write_bytes(data)
    jobs.append((key, path, kind))

# Resolve ZIP names using the same encoding and exact selection recorded during import.
portraits = json.loads((assets/'people-manifest.json').read_text())
archive = '/Users/lu/.codex/attachments/f3b7ac3e-6d3c-476e-8a2c-dda107ffcbc9/網站照片.zip'
with zipfile.ZipFile(archive) as z:
    entries = {}
    for item in z.infolist():
        try: name = item.filename.encode('cp437').decode('big5')
        except UnicodeEncodeError: name = item.filename
        entries[name] = item
    for person in portraits:
        entry = entries[person['source']]
        preserve(person['file'], z.read(entry), pathlib.PurePosixPath(person['source']).suffix, 'portrait')
for category in ('tici','hexin'):
    for item in json.loads((assets/(category+'.json')).read_text()):
        path = assets/item['file']; preserve(item['file'], path.read_bytes(), path.suffix, 'scan')
for name, value in json.loads((assets/'images.json').read_text()).items():
    header, data = value.split(',', 1)
    suffix = '.webp' if 'webp' in header else '.png' if 'png' in header else '.jpg'
    preserve('image:'+name, base64.b64decode(data), suffix, 'logo' if name=='emblem' else 'photo')
for name, value in json.loads((assets/'photos.json').read_text()).items():
    header, data = value['data'].split(',', 1)
    suffix = '.png' if 'png' in header else '.webp' if 'webp' in header else '.jpg'
    preserve('photo:'+name, base64.b64decode(data), suffix)

def optimize(job):
    key, path, kind = job
    for _ in range(300):
        if path.exists(): break
        time.sleep(1)
    data = path.read_bytes(); sha = hashlib.sha256(data).hexdigest()
    with Image.open(io.BytesIO(data)) as source:
        source.draft('RGB', (1800,1800))
        im = ImageOps.exif_transpose(source).copy()
    if im.mode not in ('RGB','RGBA'): im = im.convert('RGBA' if 'transparency' in im.info else 'RGB')
    widths = (400, 1000) if kind=='portrait' else (800, 1600)
    result = {'original': path.relative_to(assets).as_posix(), 'sha256':sha, 'originalBytes':len(data)}
    for name, size in [('small',widths[0]),('large',widths[1])]+([('thumb',480)] if key in covers or kind in ('scan','portrait') else []):
        q = 90 if kind=='scan' else 84 if name=='large' or kind=='portrait' else 80
        out = web/f'{sha[:24]}-{size}-q{q}.webp'
        resized = im.copy(); resized.thumbnail((size,int(size*1.5)), Image.Resampling.LANCZOS)
        if not out.exists(): resized.save(out,'WEBP',quality=q,lossless=kind=='logo',method=4)
        result[name] = out.relative_to(assets).as_posix()
        result[name+'Width'] = resized.width
        result[name+'Height'] = resized.height
        result[name+'Bytes'] = out.stat().st_size
    return key, result

manifest = {}; failed = []
with ThreadPoolExecutor(max_workers=6) as pool:
    futures = {pool.submit(optimize, job): job[0] for job in jobs}
    for i, future in enumerate(as_completed(futures),1):
        try:
            key, value = future.result(); manifest[key] = value
        except Exception as e: failed.append({'file':futures[future],'error':str(e)})
        if i%100==0: print('Optimized', i, '/',len(jobs),'failed',len(failed),flush=True)
(assets/'image-variants.json').write_text(json.dumps(dict(sorted(manifest.items())),ensure_ascii=False,indent=2))
(assets/'image-optimization-report.json').write_text(json.dumps({'images':len(manifest),'originalBytes':sum(x['originalBytes'] for x in manifest.values()),'smallBytes':sum(x['smallBytes'] for x in manifest.values()),'largeBytes':sum(x['largeBytes'] for x in manifest.values()),'failures':failed},ensure_ascii=False,indent=2))
print('Completed',len(manifest),'images;',len(failed),'failures',flush=True)
if failed: raise SystemExit(1)
