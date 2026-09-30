#!/usr/bin/env python3
"""政青官網：把 src/index.template.html 的佔位符注入資料
輸出：preview.html（本地預覽，圖片引用 assets/）、dist/（線上版，圖片外置到 dist/img、dist/tici、dist/hexin、dist/people、dist/files）"""
import json, re, pathlib, shutil, html as html_lib, urllib.parse, hashlib
from admin.media import public_manifest, variant_paths, safe_path
root = pathlib.Path(__file__).parent
tpl = (root/'src/index.template.html').read_text(encoding='utf-8')
imgs = json.load(open(root/'assets/images.json'))
photos = json.load(open(root/'assets/photos.json', encoding='utf-8'))
news = json.load(open(root/'assets/news.json', encoding='utf-8'))
gallery = json.load(open(root/'assets/gallery.json', encoding='utf-8'))
media = public_manifest(root)
site = json.load(open(root/'assets/site-content.json', encoding='utf-8'))
media['image:chair'] = media.get('image:chair_custom', media['people/容思瀚.webp'])
public_media = {k:{n:v for n,v in m.items() if n not in ('sha256','originalBytes','smallBytes','largeBytes','thumbBytes')} for k,m in media.items()}
# Article/album payloads carry their own image information; the homepage stays small.
for a in news + gallery:
    a['pictures'] = [public_media[p] for p in a.get('images', [])]
    if a.get('cover'):
        variant = public_media[a['cover']]
        a['thumb'] = variant.get('thumb', variant['small'])
        a['cover'] = variant['small']
def read(p): return open(root/'assets'/p, encoding='utf-8').read().strip().replace('<', '\\u003c')
people = {}
for f in sorted((root/'assets/people').glob('*.*')):
    if f.suffix.lower() in ('.jpg','.jpeg','.png','.webp'): people[f.stem] = 'people/' + f.name
try:
    import zhconv
except ImportError:
    import subprocess, sys; subprocess.run([sys.executable,'-m','pip','install','-q','zhconv']); import zhconv
def fill(html, asset_prefix, img_map, photo_map):
    html = html.replace('{{MAP_URL}}', 'https://uri.amap.com/search?keyword=' + urllib.parse.quote(site['contact_address']))
    for k, v in site.items():
        token = '{{SITE_%s}}' % k.upper()
        if token in html: html = html.replace(token, html_lib.escape(v, quote=True))
    for key in ('brands', 'sails'):
        html = html.replace('{{'+key.upper()+'}}', json.dumps(site[key], ensure_ascii=False, separators=(',',':')).replace('<', '\\u003c'))
    for k, v in img_map.items(): html = html.replace('{{IMG_%s}}' % k.upper(), v)
    html = html.replace('{{ASSET}}', asset_prefix)
    pdf = root/'assets/files/membership-form.pdf'
    if pdf.exists(): html = html.replace('files/membership-form.pdf', 'files/membership-form.pdf?v='+hashlib.sha256(pdf.read_bytes()).hexdigest()[:12])
    html = html.replace('{{PHOTOS}}', json.dumps({k:{'data':v['data'],'pos':v.get('pos',50)} for k,v in photo_map.items()}, ensure_ascii=False, separators=(',',':')).replace('<', '\\u003c'))
    rows = [dict(a, loaded=True) if asset_prefix else dict({k:v for k,v in a.items() if k not in ('body','images','links','pictures')}, body=[]) for a in news]
    html = html.replace('{{NEWS}}', json.dumps(rows, ensure_ascii=False, separators=(',',':')).replace('<', '\\u003c')).replace('{{STRUCTURE}}', read('structure.json'))
    albums = gallery if asset_prefix else [{k:v for k,v in g.items() if k not in ('images','pictures')} for g in gallery]
    html = html.replace('{{GALLERY}}', json.dumps(albums, ensure_ascii=False, separators=(',',':')).replace('<', '\\u003c'))
    html = html.replace('{{PEOPLE}}', json.dumps(people, ensure_ascii=False).replace('<', '\\u003c')).replace('{{TICI}}', read('tici.json')).replace('{{HEXIN}}', read('hexin.json'))
    html = html.replace('{{MEDIA}}', json.dumps({k:m for k,m in public_media.items() if not k.startswith('legacy/')}, ensure_ascii=False, separators=(',',':')).replace('<', '\\u003c'))
    chars = sorted(set(re.findall(r'[㐀-鿿]', html + read('news.json'))))
    chars = sorted(set(chars) | set(''.join(zhconv.convert(c, region) for c in chars for region in ('zh-cn', 'zh-hk'))))
    t2s = {c: zhconv.convert(c,'zh-cn') for c in chars}; t2s = {c:s for c,s in t2s.items() if s!=c}
    s2t = {c: zhconv.convert(c,'zh-hk') for c in chars}; s2t = {c:t for c,t in s2t.items() if t!=c}
    html = html.replace('{{T2S}}', json.dumps(t2s, ensure_ascii=False, separators=(',',':')))
    html = html.replace('{{S2T}}', json.dumps(s2t, ensure_ascii=False, separators=(',',':')))
    assert '{{' not in html, 'leftover placeholder: ' + re.findall(r'\{\{[A-Z_]+\}\}', html)[0]
    return html, len(t2s)
head = ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<meta name="color-scheme" content="light dark">')
# ---- preview.html：本地單檔（圖片 base64 內嵌，題詞/賀信/照片引用 assets/）----
preview_imgs = {k:'assets/'+media['image:'+k]['large'] for k in imgs}
preview_imgs['hero_m'] = 'assets/'+media['image:hero']['small']
preview_imgs['chair'] = 'assets/'+media['image:chair']['small']
preview_photos = {k:dict(v,data='assets/'+media['photo:'+k]['small']) for k,v in photos.items()}
html, n = fill(tpl, 'assets/', preview_imgs, preview_photos)
(root/'preview.html').write_text(head+'<link rel="icon" href="'+preview_imgs['emblem']+'"></head><body style="margin:0">'+html+'</body></html>', encoding='utf-8')
(root/'index.html').write_text((root/'preview.html').read_text(encoding='utf-8'), encoding='utf-8')
# ---- dist/：線上版，全部圖片外置 ----
dist = root/'dist'
data = dist/'data'; (data/'articles').mkdir(parents=True, exist_ok=True)
(data/'albums').mkdir(parents=True, exist_ok=True)
for folder, rows in (("articles", news), ("albums", gallery)):
    expected = {str(row['id'])+'.json' for row in rows}
    for stale in (data/folder).glob('*.json'):
        if stale.name not in expected: stale.unlink()
for g in gallery: (data/'albums'/f'{g["id"]}.json').write_text(json.dumps(g, ensure_ascii=False, separators=(',',':')), encoding='utf-8')
(data/'news.json').write_text(json.dumps([{k:v for k,v in a.items() if k!='pictures'} for a in news], ensure_ascii=False, separators=(',',':')), encoding='utf-8')
for kind in ('news','media'):
    (data/f'search-{kind}.json').write_text(json.dumps([{'id':a['id'],'body':a['body']} for a in news if a['category']==kind], ensure_ascii=False, separators=(',',':')), encoding='utf-8')
for a in news: (data/'articles'/f'{a["id"]}.json').write_text(json.dumps(a, ensure_ascii=False, separators=(',',':')), encoding='utf-8')
img_ext = {k:media['image:'+k]['large'] for k in imgs}
img_ext['hero_m'] = media['image:hero']['small']
img_ext['chair'] = media['image:chair']['small']
photo_ext = {k: {'data': media['photo:'+k]['small'], 'pos': v.get('pos',50)} for k, v in photos.items()}
publish_files = variant_paths(media) | set(people.values())
for folder in ('tici', 'hexin', 'files'):
    publish_files.update(p.relative_to(root/'assets').as_posix() for p in (root/'assets'/folder).rglob('*') if p.is_file())
for relative in publish_files:
    source = safe_path(root/'assets', relative)
    if source.is_file():
        destination = safe_path(dist, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
(dist/'.publish-files.json').write_text(json.dumps(sorted(publish_files)), encoding='utf-8')
html2, n2 = fill(tpl, '', img_ext, photo_ext)
(dist/'index.html').write_text(head+'<link rel="icon" href="'+img_ext['emblem']+'"></head><body style="margin:0">'+html2+'</body></html>', encoding='utf-8')
print(f'preview.html {len(html)//1024} KB · dist/index.html {len(html2)//1024} KB · 簡繁字表 {n2} 對 · 人物照片 {len(people)} 張')
