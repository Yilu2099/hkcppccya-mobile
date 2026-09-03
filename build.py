#!/usr/bin/env python3
"""政青手機版：把 src/index.template.html 的佔位符注入資料，輸出 index.html（Artifact 用）與 preview.html（完整檔，可直接打開 / 上線）"""
import json, re, pathlib
root = pathlib.Path(__file__).parent
html = (root/'src/index.template.html').read_text(encoding='utf-8')
imgs = json.load(open(root/'assets/images.json'))
for k, v in imgs.items():
    html = html.replace('{{IMG_%s}}' % k.upper(), v)
photos = json.load(open(root/'assets/photos.json', encoding='utf-8'))
html = html.replace('{{PHOTOS}}', json.dumps({k:{'data':v['data'],'pos':v.get('pos',50)} for k,v in photos.items()}, ensure_ascii=False, separators=(',',':')))
html = html.replace('{{NEWS}}', open(root/'assets/news.json', encoding='utf-8').read().strip())
html = html.replace('{{LEADERS}}', open(root/'assets/leaders.json', encoding='utf-8').read().strip())
try:
    import zhconv
except ImportError:
    import subprocess, sys; subprocess.run([sys.executable,'-m','pip','install','-q','zhconv']); import zhconv
chars = sorted(set(re.findall(r'[㐀-鿿]', html)))
t2s = {c: zhconv.convert(c,'zh-cn') for c in chars}; t2s = {c:s for c,s in t2s.items() if s!=c}
html = html.replace('{{T2S}}', json.dumps(t2s, ensure_ascii=False, separators=(',',':')))
assert '{{' not in html.replace('{{}}',''), 'leftover placeholder'
(root/'index.html').write_text(html, encoding='utf-8')
wrapped = ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
           '<meta name="color-scheme" content="light dark"><link rel="icon" href="'+imgs['emblem']+'"></head><body style="margin:0">'+html+'</body></html>')
(root/'preview.html').write_text(wrapped, encoding='utf-8')
# ---- dist/：圖片改為外部檔案，線上版用（HTML 由 1.5MB 降到約 150KB，圖片按需載入、可長期快取）----
import base64, shutil, hashlib
dist = root/'dist'; (dist/'img').mkdir(parents=True, exist_ok=True)
def ext_file(name, datauri):
    head, b64 = datauri.split(',', 1); ext = 'png' if 'png' in head else 'jpg'
    data = base64.b64decode(b64); h = hashlib.md5(data).hexdigest()[:8]
    fn = f'{name}.{h}.{ext}'; (dist/'img'/fn).write_bytes(data); return 'img/'+fn
h2 = (root/'src/index.template.html').read_text(encoding='utf-8')
for k, v in imgs.items(): h2 = h2.replace('{{IMG_%s}}' % k.upper(), ext_file(k, v))
h2 = h2.replace('{{PHOTOS}}', json.dumps({k:{'data':ext_file(k, v['data']),'pos':v.get('pos',50)} for k,v in photos.items()}, ensure_ascii=False, separators=(',',':')))
h2 = h2.replace('{{NEWS}}', open(root/'assets/news.json', encoding='utf-8').read().strip())
h2 = h2.replace('{{LEADERS}}', open(root/'assets/leaders.json', encoding='utf-8').read().strip())
h2 = h2.replace('{{T2S}}', json.dumps(t2s, ensure_ascii=False, separators=(',',':')))
wrapped2 = ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="color-scheme" content="light dark"><link rel="icon" href="'+ext_file('favicon', imgs['emblem'])+'">'
            '<link rel="preload" as="image" href="'+ext_file('hero', imgs['hero'])+'"></head><body style="margin:0">'+h2+'</body></html>')
(dist/'index.html').write_text(wrapped2, encoding='utf-8')
print('index.html', len(html)//1024, 'KB · 簡繁字表', len(t2s), '對 · preview.html written · dist/index.html', len(wrapped2)//1024, 'KB +', len(list((dist/'img').iterdir())), 'images')
