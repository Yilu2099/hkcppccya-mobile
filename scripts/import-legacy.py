"""Import public content from authenticated legacy HTML snapshots, without credentials."""
import argparse,json,pathlib,re,urllib.parse,urllib.request,hashlib,io,time,html
from concurrent.futures import ThreadPoolExecutor,as_completed
from bs4 import BeautifulSoup
from PIL import Image,ImageOps
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('snapshot_dir',type=pathlib.Path);args=p.parse_args();src=args.snapshot_dir
assets=ROOT/'assets';media=assets/'legacy';media.mkdir(exist_ok=True)
def dump(name,data):(assets/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def text(x):return re.sub(r'[\t\r ]+',' ',x.get_text('\n',strip=True)).strip()
def safe_url(u):
 u=urllib.parse.urljoin('https://hkcppccya.org/',u.strip())
 return u if urllib.parse.urlsplit(u).scheme in ('http','https') else ''
urls=set();news=[];gallery=[];issues=[];excluded=[]
for parent in (3,5):
 for row in BeautifulSoup((src/f'news-table-{parent}.html').read_text(),'html.parser').select('.table_list'):
  a=row.find('a')
  if a and not a.text.strip():excluded.append({'source':a['href'],'reason':'empty title'})
for path,parent in json.loads((src/'article-index.json').read_text()):
 f=src/path.replace('?','_').replace('=','-')
 if not f.exists():issues.append({'source':path,'issue':'unavailable'});continue
 s=BeautifulSoup(f.read_text(),'html.parser')
 def value(name):
  x=s.find(attrs={'name':name});return (x.get('value','') if x.name=='input' else html.unescape(x.decode_contents())) if x else ''
 raw=value('news_content_1');body=BeautifulSoup(raw,'html.parser')
 for el in body(['script','style']):el.decompose()
 paragraphs=[x.strip() for x in re.split(r'\n\s*\n',text(body)) if x.strip()]
 pics=list(dict.fromkeys(safe_url(i.get('src','')) for i in body.select('img[src]') if not i.get('src','').lower().endswith('thumbs.db')));pics=[u for u in pics if u];urls.update(pics)
 links=[{'title':a.get_text(' ',strip=True) or '原文連結','url':safe_url(a['href'])} for a in body.select('a[href]') if safe_url(a['href'])]
 if value('link_1'):links.insert(0,{'title':'閱讀原文','url':safe_url(value('link_1'))})
 item={'id':int(value('newsid')),'title':value('news_headline_1').strip(),'date':value('post_date'),'body':paragraphs,'category':'media' if parent==5 else 'news'}
 for tag,pattern in [('tour','旅學團'),('national','國情班|國情研修|兩會.*學習'),('policy','政情班|與司長有約'),('mentor','導師計劃|社青共融')]:
  if re.search(pattern,item['title']):item['tag']=tag;break
 if pics:item['images']=pics
 if links:item['links']=links
 if not paragraphs and not links and not pics:issues.append({'source':path,'issue':'empty body'})
 news.append(item)
for a in json.loads((src/'album-index.json').read_text()):
 page=src/f'pages_edit.asp_pageid-{a["id"]}';album=src/f'album.asp_parentid-{a["id"]}'
 if not page.exists() or not album.exists():issues.append({'source':str(a['id']),'issue':'album unavailable'});continue
 s=BeautifulSoup(page.read_text(),'html.parser');status=s.select_one('input[name="status"][checked]')
 if not status or status.get('value')!='Yes':continue
 s=BeautifulSoup(album.read_text(),'html.parser');pics=list(dict.fromkeys(safe_url(i.get('src','')) for i in s.select('img[src]') if i.get('src','').startswith('/Files/') and not i.get('src','').lower().endswith('thumbs.db')))
 if not pics:issues.append({'source':str(a['id']),'issue':'empty album'});continue
 m=re.match(r'^(?:20\d{2}年)?(\d{1,2})月(?:(\d{1,2})日)?',a['title'])
 date=a['year']+(f'-{int(m[1]):02d}'+(f'-{int(m[2]):02d}' if m[2] else '') if m else '')
 urls.update(pics);gallery.append({'id':'album'+str(a['id']),'title':a['title'],'date':date,'images':pics})
print('Content',len(news),'Albums',len(gallery),'Images',len(urls),flush=True)
failed=[];mapping={}
def download(u):
 key=hashlib.sha256(u.encode()).hexdigest()[:16];f=media/(key+'.webp')
 if f.exists():
  try:Image.open(f).verify()
  except Exception:f.unlink()
 if not f.exists():
  for attempt in range(3):
   try:
    parts=urllib.parse.urlsplit(u);url=urllib.parse.urlunsplit((parts.scheme,parts.netloc,urllib.parse.quote(urllib.parse.unquote(parts.path),safe='/'),parts.query,''))
    data=urllib.request.urlopen(url,timeout=20).read();im=ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert('RGB');im.thumbnail((1600,1600),Image.Resampling.LANCZOS);tmp=f.with_suffix('.tmp');im.save(tmp,'WEBP',quality=83,method=4);tmp.replace(f);break
   except Exception as e:
    if attempt==2:return u,None,str(e)
 return u,'legacy/'+f.name,None
with ThreadPoolExecutor(max_workers=6) as pool:
 for i,ft in enumerate(as_completed([pool.submit(download,u) for u in urls]),1):
  u,name,error=ft.result()
  if name:mapping[u]=name
  else:failed.append({'url':u,'error':error})
  if i%100==0:print('Images',i,'/',len(urls),'failed',len(failed),flush=True)
for a in news+gallery:
 if 'images' in a:a['images']=[mapping[u] for u in a['images'] if u in mapping]
 if a.get('images'):
  a['cover']=a['images'][0]
  source=assets/a['cover'];thumb=source.with_name(source.stem+'-thumb.webp')
  if not thumb.exists():
   im=Image.open(source);im.thumbnail((480,480),Image.Resampling.LANCZOS);im.save(thumb,'WEBP',quality=80,method=4)
  a['thumb']='legacy/'+thumb.name
# Preserve known cover positioning for the newest stories; album dates use linked article dates.
for g in gallery:
 matches=[a for a in news if a['category']=='news' and re.sub(r'\s','',a['title'])==re.sub(r'\s','',g['title'])]
 if matches:
  article=matches[0];g['news']=article['id'];g['date']=article['date']
  if not article.get('images'):article['images']=g['images'];article['cover']=g['cover'];article['thumb']=g['thumb']
news.sort(key=lambda a:(a['date'],a['id']),reverse=True);gallery.sort(key=lambda a:(a['date'],int(a['id'][5:])),reverse=True)
dump('news.json',news);dump('gallery.json',gallery)
report={'source':'https://hkcppccya.org/admin/','news':sum(a['category']=='news' for a in news),'media':sum(a['category']=='media' for a in news),'albums':len(gallery),'images':len(mapping),'imageBytes':sum((assets/v).stat().st_size for v in mapping.values()),'excludedRecords':excluded,'issues':issues,'missingImages':failed}
dump('migration-report.json',report);print(json.dumps({k:v for k,v in report.items() if k not in ('issues','missingImages')},ensure_ascii=False),flush=True)
