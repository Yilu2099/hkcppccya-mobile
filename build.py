#!/usr/bin/env python3
"""政青官網：把 src/index.template.html 的佔位符注入資料
輸出：preview.html（本地預覽，圖片引用 assets/）、dist/（線上版，圖片外置到 dist/img、dist/tici、dist/hexin、dist/people、dist/files）"""
import json, re, pathlib, base64, hashlib, shutil, os
root = pathlib.Path(__file__).parent
tpl = (root/'src/index.template.html').read_text(encoding='utf-8')
imgs = json.load(open(root/'assets/images.json'))
photos = json.load(open(root/'assets/photos.json', encoding='utf-8'))
def read(p): return open(root/'assets'/p, encoding='utf-8').read().strip()
people = {}
for f in sorted((root/'assets/people').glob('*.*')):
    if f.suffix.lower() in ('.jpg','.jpeg','.png'): people[f.stem] = 'people/' + f.name
try:
    import zhconv
except ImportError:
    import subprocess, sys; subprocess.run([sys.executable,'-m','pip','install','-q','zhconv']); import zhconv
def fill(html, asset_prefix, img_map, photo_map):
    for k, v in img_map.items(): html = html.replace('{{IMG_%s}}' % k.upper(), v)
    html = html.replace('{{ASSET}}', asset_prefix)
    html = html.replace('{{PHOTOS}}', json.dumps({k:{'data':v['data'],'pos':v.get('pos',50)} for k,v in photo_map.items()}, ensure_ascii=False, separators=(',',':')))
    html = html.replace('{{NEWS}}', read('news.json')).replace('{{STRUCTURE}}', read('structure.json'))
    html = html.replace('{{PEOPLE}}', json.dumps(people, ensure_ascii=False)).replace('{{TICI}}', read('tici.json')).replace('{{HEXIN}}', read('hexin.json'))
    chars = sorted(set(re.findall(r'[㐀-鿿]', html)))
    t2s = {c: zhconv.convert(c,'zh-cn') for c in chars}; t2s = {c:s for c,s in t2s.items() if s!=c}
    html = html.replace('{{T2S}}', json.dumps(t2s, ensure_ascii=False, separators=(',',':')))
    assert '{{' not in html, 'leftover placeholder: ' + re.findall(r'\{\{[A-Z_]+\}\}', html)[0]
    return html, len(t2s)
head = ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<meta name="color-scheme" content="light dark">')
# ---- preview.html：本地單檔（圖片 base64 內嵌，題詞/賀信/照片引用 assets/）----
html, n = fill(tpl, 'assets/', imgs, photos)
(root/'preview.html').write_text(head+'<link rel="icon" href="'+imgs['emblem']+'"></head><body style="margin:0">'+html+'</body></html>', encoding='utf-8')
# ---- dist/：線上版，全部圖片外置 ----
dist = root/'dist'
for d in ('img','tici','hexin','people','files'): (dist/d).mkdir(parents=True, exist_ok=True)
def ext_file(name, datauri):
    headr, b64 = datauri.split(',', 1); ext = 'svg' if 'svg' in headr else ('png' if 'png' in headr else 'jpg')
    data = base64.b64decode(b64); h = hashlib.md5(data).hexdigest()[:8]
    fn = f'{name}.{h}.{ext}'; (dist/'img'/fn).write_bytes(data); return 'img/'+fn
img_ext = {k: ext_file(k, v) for k, v in imgs.items()}
photo_ext = {k: {'data': ext_file(k, v['data']), 'pos': v.get('pos',50)} for k, v in photos.items()}
for d in ('tici','hexin','people','files'):
    if (root/'assets'/d).exists(): shutil.copytree(root/'assets'/d, dist/d, dirs_exist_ok=True)
html2, n2 = fill(tpl, '', img_ext, photo_ext)
(dist/'index.html').write_text(head+'<link rel="icon" href="'+img_ext['emblem']+'"><link rel="preload" as="image" href="'+img_ext['hero_m']+'"></head><body style="margin:0">'+html2+'</body></html>', encoding='utf-8')
print(f'preview.html {len(html)//1024} KB · dist/index.html {len(html2)//1024} KB · 簡繁字表 {n2} 對 · 人物照片 {len(people)} 張')
