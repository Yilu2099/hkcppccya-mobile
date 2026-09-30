const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {news:'消息与报道',gallery:'活动相册',structure:'本会架构',site:'页面文字',tici:'题词',hexin:'贺信',people:'人物照片',pictures:'网站图片',files:'入会表格'};
const hints = {news:'查找或新增消息，编辑标题、正文和相片。',gallery:'管理活动相册与封面相片。',structure:'编辑执委会、工作委员会和历届名单。',site:'修改首页、关于本会及联系资料。',tici:'管理题词内容与图片。',hexin:'管理贺信内容与图片。',people:'按姓名上传或更换人物照片。',pictures:'更换首页和网站使用的图片。',files:'上传新版会员登记表 PDF。'};
const groups = [['日常更新',['news','gallery']],['网站页面',['site','structure','tici','hexin']],['图片与文件',['people','pictures','files']]];
const names = {title:'标题',date:'日期',category:'文章分类',body:'正文',tag:'活动系列',news:'相关消息编号（可留空）',name:'姓名',region:'地区',kind:'类别',motto:'题词内容',page:'同一机构第几页',exec:'执委会',committees:'工作委员会',honor:'荣誉架构',fund:'基金架构',past:'历届领袖',roles:'职务',names:'名单',chair:'主席',term:'届别',now:'现任',home_motto:'首页宗旨',home_subtitle:'首页副标题',home_banner_title:'横幅标题',home_banner_date:'横幅日期',home_banner_article:'横幅关联文章编号',home_emblem:'会徽介绍',home_join_title:'加入区标题',home_join_text:'加入区说明',home_chair_1:'首页主席寄语',stats_years:'成立年数',stats_members:'会员人数',stats_brands:'品牌活动数量',stats_committees:'工作委员会数量',contact_address:'联系地址',contact_phone_display:'电话号码',contact_phone_digits:'电话拨号号码',contact_whatsapp_display:'WhatsApp 号码',contact_whatsapp_digits:'WhatsApp 拨号号码',contact_fax_display:'传真号码',contact_email:'联系邮箱',contact_wechat:'微信 ID',programmes_intro:'品牌活动介绍',tributes_intro:'题词贺信介绍',brands:'四大品牌活动',sails:'五帆精神',n:'显示编号',desc:'卡片简介',long:'详细说明'};
const label = k => names[k] || k.replace(/^(about_intro|chair_message|join_why)_(\d+)$/, (_,a,n) => ({about_intro:'本会简介',chair_message:'主席的话',join_why:'加入说明'}[a]+' '+n)).replaceAll('_',' ');
const collection = () => ['news','gallery','tici','hexin'].includes(section);
let csrf='', section='news', view='list', data=null, revision='', selected=0, dirty=false, media={}, publicSite=false, query='', limit=50, busy=false;

function notice(message, bad=false){const box=$('#notice');box.textContent=message;box.classList.toggle('error',bad)}
function actions(){
  $('#back-list').hidden=!collection()||view!=='editor';
  $('#save').hidden=['people','pictures','files'].includes(section)||collection()&&view==='list'&&!dirty;
  $('#save').disabled=!dirty;

  $('#breadcrumb').textContent=collection()&&view==='editor'?`${labels[section]} / 编辑内容`:'网站内容';
  $('#section-title').textContent=collection()&&view==='editor'?(data[selected]?.title?'编辑':'新增')+labels[section]:labels[section];
  $('#section-hint').textContent=collection()&&view==='editor'?'保存后官网立即更新。':hints[section];
  document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('on',b.dataset.section===section));
}
async function working(message, task){
  if(busy)return;
  busy=true;notice(message);$('#app').setAttribute('aria-busy','true');
  $('#workspace').inert=true;$('#nav').inert=true;$('.actions').inert=true;$('#logout').disabled=true;
  try{await task()}catch(err){notice(err.message||'网络连接失败，请重试。',true)}
  finally{busy=false;$('#app').removeAttribute('aria-busy');$('#workspace').inert=false;$('#nav').inert=false;$('.actions').inert=false;$('#logout').disabled=false;actions()}
}
function changed(){dirty=true;actions();notice('有未保存的修改。')}
async function api(path, body){
  const opt={credentials:'same-origin'};
  if(body!==undefined){opt.method='POST';opt.headers={'Content-Type':'application/json','X-CSRF':csrf};opt.body=JSON.stringify(body)}
  const res=await fetch('/cms/api/'+path,opt), value=await res.json();
  if(!res.ok)throw Error(res.status===401&&path!=='login'?'登录已过期。请另开一个后台窗口重新登录，再回到这里保存，当前编辑内容仍保留。':value.error||'请求失败');
  return value;
}
async function boot(){
  const session=await api('session');
  $('#register').hidden=true;
  if(!session.loggedIn){$('#login').hidden=false;$('#app').hidden=true;return}
  cmsRestorePreference();
  csrf=session.csrf;$('#invite').hidden=session.user.role!=='admin';$('#current-account').textContent=session.user.role==='admin'?'管理员':session.user.account;publicSite=session.public;media=await api('media');
  $('#login').hidden=true;$('#app').hidden=false;
  $('#nav').innerHTML=groups.map(([name,keys])=>`<div class="nav-group"><div class="nav-group-title">${name}</div>${keys.map(k=>`<button data-section="${k}">${labels[k]}</button>`).join('')}</div>`).join('');
  await openSection(section);
}
async function openSection(name){
  if(busy)return;
  if(dirty&&!cmsConfirm('当前修改还没保存，确定放弃修改吗？'))return;
  await working('正在加载…',async()=>{
    const value=['people','pictures','files'].includes(name)?null:await api('data/'+name);
    section=name;view=collection()?'list':'editor';dirty=false;query='';limit=50;selected=0;
    const box=$('#workspace');box.oninput=null;box.onclick=null;
    data=value?.data;revision=value?.revision;
    if(value)render();else await renderMediaPage();
    actions();notice('');scrollTo(0,0);
  });
}
function render(){collection()?renderCollection():renderObject()}
function rowTitle(row,i){return (section==='tici'?row.name:row.title)||row.title||row.name||row.region||'第 '+(i+1)+' 条'}
function rowInfo(row){return [row.date,section==='news'?(row.category==='media'?'报道及专访':'活动消息'):section==='tici'?row.title:row.region||row.name].filter(Boolean).join(' · ')}
function renderCollection(){view==='list'?renderList():renderEditor();actions()}
function renderList(){
  $('#workspace').oninput=null;$('#workspace').onclick=null;
  $('#workspace').innerHTML=`<div class="collection"><div class="collection-head"><span id="list-meta" class="collection-meta"></span><div class="collection-controls"><input id="search" type="search" aria-label="搜索内容" placeholder="搜索标题、姓名或日期" value="${esc(query)}"><button id="add" class="primary">＋ 新增</button></div></div><div id="rows"></div></div>`;
  $('#search').oninput=e=>{query=e.target.value;limit=50;renderRows()};
  $('#add').onclick=addRow;
  renderRows();
}
function renderRows(){
  const matches=data.map((row,i)=>({row,i})).filter(({row})=>!query||cmsSearchText([row.title,row.name,row.date,row.region].join(' ')).includes(cmsSearchText(query.trim())));
  $('#list-meta').textContent=query?`找到 ${matches.length} 条结果`:`共 ${data.length} 条`;
  $('#rows').innerHTML=matches.slice(0,limit).map(({row,i})=>`<button class="item-row" data-index="${i}"><span><b>${esc(rowTitle(row,i))}</b><small>${esc(rowInfo(row))}</small></span><span class="arrow">›</span></button>`).join('')||'<div class="empty">没有找到内容，请换个关键词。</div>';
  if(matches.length>limit)$('#rows').insertAdjacentHTML('beforeend',`<button class="more" id="more">继续显示（还剩 ${matches.length-limit} 条）</button>`);
  $('#rows').onclick=e=>{if(e.target.id==='more'){limit+=50;renderRows();return}const row=e.target.closest('[data-index]');if(row){selected=+row.dataset.index;view='editor';renderCollection();scrollTo(0,0)}};
}
function addRow(){
  if(section==='news')data.unshift({id:Math.max(0,...data.map(x=>Number(x.id)||0))+1,title:'',date:new Date().toLocaleDateString('sv-SE'),body:[],category:'news',images:[],cover:''});
  else if(section==='gallery')data.unshift({id:'album'+Date.now(),title:'',date:new Date().toLocaleDateString('sv-SE'),images:[],cover:''});
  else data.unshift(section==='tici'?{id:'t'+Date.now(),file:'',thumb:'',name:'',title:'',motto:''}:{id:'h'+Date.now(),region:'',kind:'',title:'',page:1,file:'',thumb:''});
  selected=0;view='editor';changed();renderCollection();scrollTo(0,0);
}
function input(key,value,type='text',opts=''){
  return `<label class="field"><span>${section==='tici'&&key==='title'?'职务':label(key)}</span>${type==='textarea'?`<textarea data-field="${key}" ${opts}>${esc(value)}</textarea>`:type==='select'?`<select data-field="${key}"><option value="news" ${value==='news'?'selected':''}>活动消息</option><option value="media" ${value==='media'?'selected':''}>报道及专访</option></select>`:`<input data-field="${key}" type="${type}" value="${esc(value)}" ${opts}>`}</label>`;
}
function photoEditor(row){
  return `<div class="field"><span>相片 <small>选择封面，或用箭头调整相片顺序</small></span><div class="photos">${(row.images||[]).map((key,i)=>`<div class="photo">${row.cover===key?'<span class="cover">封面</span>':''}<img src="/cms/media/${esc(media[key]||key)}" loading="lazy" alt=""><div class="bar"><button data-photo="cover" data-i="${i}" title="设为封面">封面</button><button data-photo="up" data-i="${i}" title="向前" ${i===0?'disabled':''}>↑</button><button data-photo="down" data-i="${i}" title="向后" ${i===row.images.length-1?'disabled':''}>↓</button><button data-photo="remove" data-i="${i}" title="移除">×</button></div></div>`).join('')}</div><label class="drop"><b>＋ 添加相片</b><span>支持多选；系统自动压缩网页图片并保留原图</span><input id="upload-photos" type="file" accept="image/jpeg,image/png,image/webp" multiple></label></div>`;
}
function renderEditor(){
  const row=data[selected];
  if(!row){$('#workspace').innerHTML='<div class="empty">这条内容不存在，请返回列表。</div>';return}
  let html=`<div class="edit-shell ${['tici','hexin'].includes(section)?'tribute-editor':''}">`;
  if(section==='news'||section==='gallery'){
    html+=`<section class="edit-card"><h2>基本信息</h2><div class="fields">${input('title',row.title,'text','placeholder="请输入清楚的标题"')}`;
    html+=`<div class="two">${input('date',row.date,section==='news'?'date':'text',section==='gallery'?'placeholder="YYYY-MM-DD，也可只填年份"':'')}${section==='news'?input('category',row.category,'select'):input('news',row.news||'','number','placeholder="可不填"')}</div></div></section>`;
    if(section==='news'){
      html+=`<section class="edit-card"><h2>文章正文</h2><p class="hint">直接输入文字，段落之间空一行。</p>${input('body',(row.body||[]).join('\n\n'),'textarea','class="long" placeholder="在这里填写文章内容"')}</section>`;
    }
    html+=`<section class="edit-card"><h2>相片与封面</h2>${photoEditor(row)}</section>`;
    if(section==='news')html+=`<section class="edit-card"><details><summary>更多设置：活动系列与相关链接</summary><div class="fields"><label class="field"><span>活动系列（可留空）</span><select data-field="tag"><option value="">不分类</option>${[['tour','旅学团'],['national','国情班'],['policy','政情班'],['mentor','青年导师计划']].map(([key,text])=>`<option value="${key}" ${row.tag===key?'selected':''}>${text}</option>`).join('')}</select></label><div class="field"><span>相关文章链接</span>${(row.links||[]).map((link,i)=>`<div class="two"><input data-link="title" data-i="${i}" placeholder="链接名称" value="${esc(link.title)}"><input data-link="url" data-i="${i}" placeholder="https://…" value="${esc(link.url)}"><button class="danger" data-remove-link="${i}" type="button">移除链接</button></div>`).join('')}<button id="add-link" type="button">＋ 添加链接</button></div></div></details></section>`;
  }else{
    html+=`<section class="edit-card"><h2>${section==='tici'?'题词资料':'贺信资料'}</h2><div class="fields">`;
    if(section==='tici')html+=input('name',row.name||'')+input('title',row.title||'')+input('motto',row.motto||'','textarea');
    else html+=input('title',row.title||'')+`<div class="two">${input('region',row.region||'')}${input('kind',row.kind||'')}</div>`;
    if(section==='hexin')html+=input('page',row.page||1,'number','min="1"');
    html+=`</div></section><section class="edit-card"><h2>图片</h2>${row.file?`<img src="/cms/media/${esc(media[row.file]||row.file)}" style="max-width:100%;max-height:240px;object-fit:contain;margin-bottom:14px" alt="当前图片">`:''}<label class="drop"><b>＋ 上传或替换图片</b><span>自动生成适合网页的图片</span><input id="upload-single" type="file" accept="image/jpeg,image/png,image/webp"></label></section>`;
  }
  html+=`<div class="editor-tools"><button id="delete" class="danger" type="button">删除这一条</button></div></div>`;
  $('#workspace').innerHTML=html;
  const box=$('#workspace');
  box.oninput=e=>{
    if(e.target.dataset.link){row.links[+e.target.dataset.i][e.target.dataset.link]=e.target.value;changed();return}
    const key=e.target.dataset.field;if(!key)return;
    let value=e.target.value;
    if(key==='body')value=value.split(/\n\s*\n/).map(s=>s.trim()).filter(Boolean);
    if(key==='news'||key==='page')value=value?+value:null;
    row[key]=value;changed();
  };
  box.onclick=e=>{
    if(e.target.id==='delete'){if(cmsConfirm('确定删除这条内容？保存后才会生效。')){data.splice(selected,1);selected=0;view='list';changed();renderCollection()}return}
    if(e.target.id==='add-link'){(row.links??=[]).push({title:'',url:''});changed();renderEditor();return}
    const remove=e.target.closest('[data-remove-link]');if(remove){row.links.splice(+remove.dataset.removeLink,1);changed();renderEditor();return}
    const button=e.target.closest('[data-photo]');if(!button)return;
    const i=+button.dataset.i,key=row.images[i];
    if(button.dataset.photo==='cover')row.cover=key;
    if(button.dataset.photo==='up'&&i>0)[row.images[i-1],row.images[i]]=[row.images[i],row.images[i-1]];
    if(button.dataset.photo==='down'&&i<row.images.length-1)[row.images[i+1],row.images[i]]=[row.images[i],row.images[i+1]];
    if(button.dataset.photo==='remove'){row.images.splice(i,1);if(row.cover===key)row.cover=row.images[0]||''}
    changed();renderEditor();
  };
  const uploadInput=$('#upload-photos')||$('#upload-single');
  if(uploadInput)uploadInput.onchange=()=>working('正在处理图片…',async()=>{
    try{for(const file of uploadInput.files){notice('正在处理 '+file.name+'…');const key=await upload(file);if(section==='news'||section==='gallery'){row.images.push(key);if(!row.cover)row.cover=key}else{row.file=key;row.thumb=key}changed()}}
    finally{renderEditor()}
    notice('图片已加入，点击「保存修改」后官网更新。');
  });
}
function pathCode(path){return encodeURIComponent(JSON.stringify(path))}
function getAt(path){return path.reduce((obj,key)=>obj[key],data)}
function setAt(path,value){path.slice(0,-1).reduce((obj,key)=>obj[key],data)[path.at(-1)]=value;changed()}
function blank(value){if(Array.isArray(value))return [];if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,blank(item)]));return typeof value==='boolean'?false:typeof value==='number'?0:''}
function valueField(path,value,title){
  if(typeof value==='boolean')return `<label class="check-field"><input type="checkbox" data-value="${pathCode(path)}" ${value?'checked':''}>${esc(title)}</label>`;
  const code=pathCode(path),long=String(value).length>60||/intro|message|text|motto|desc|long|join_why/.test(path.join('.'));
  return `<label class="field ${long?'long':''}"><span>${esc(title)}</span>${long?`<textarea data-value="${code}">${esc(value)}</textarea>`:`<input data-value="${code}" value="${esc(value)}" type="${typeof value==='number'?'number':'text'}">`}</label>`;
}
function tree(value,path=[],name=''){
  if(Array.isArray(value)){
    if(value.every(item=>typeof item==='string'))return `<label class="field"><span>${esc(label(name))}</span><textarea data-lines="${pathCode(path)}" placeholder="每行一个">${esc(value.join('\n'))}</textarea><small>每行一位或一条</small></label>`;
    return `<div class="generic-group"><h3>${esc(label(name))}</h3>${value.map((item,i)=>`<details data-path="${pathCode([...path,i])}" ${i===0&&value.length<8?'open':''}><summary>${esc(item.title||item.name||item.region||'第 '+(i+1)+' 项')}</summary><div class="fields">${tree(item,[...path,i])}</div><div class="generic-actions"><button class="danger" data-remove="${pathCode([...path,i])}">删除</button></div></details>`).join('')}<button data-add="${pathCode(path)}">＋ 新增${esc(label(name))}</button></div>`;
  }
  if(value&&typeof value==='object')return `<div class="fields">${Object.entries(value).map(([key,item])=>tree(item,[...path,key],key)).join('')}</div>`;
  return valueField(path,value,name==='name'&&path[0]==='committees'?'委员会名称':label(name));
}
const siteGroups=[['首页',['home_motto','home_subtitle','home_banner_title','home_banner_date','home_banner_article','home_emblem','home_chair_1']],['关于本会',['about_intro_1','about_intro_2','about_intro_3','chair_message_1','chair_message_2','chair_message_3','chair_message_4']],['加入政青',['home_join_title','home_join_text','join_why_1','join_why_2','join_why_3']],['活动与数据',['programmes_intro','tributes_intro','stats_years','stats_members','stats_brands','stats_committees']],['联系资料',['contact_address','contact_phone_display','contact_whatsapp_display','contact_fax_display','contact_email','contact_wechat']]];
function renderSite(){
  let html='<div class="edit-shell">';
  for(const [title,keys] of siteGroups)html+=`<details class="section-card"><summary>${title}</summary><div class="fields site-fields">${keys.filter(key=>key in data).map(key=>valueField([key],data[key],label(key))).join('')}</div></details>`;
  html+=`<details class="section-card"><summary>四大品牌活动</summary>${Object.entries(data.brands).map(([key,item])=>`<details><summary>${esc(item.name)}</summary><div class="fields">${['n','name','tag','desc','long'].map(field=>valueField(['brands',key,field],item[field],field==='tag'?'显示标签':field==='name'?'活动名称':label(field))).join('')}</div></details>`).join('')}</details>`;
  html+=`<details class="section-card"><summary>五帆精神</summary><div class="fields">${data.sails.map((item,i)=>`<div class="two">${valueField(['sails',i,0],item[0],'第 '+(i+1)+' 帆标题')}${valueField(['sails',i,1],item[1],'说明')}</div>`).join('')}</div></details></div>`;
  $('#workspace').innerHTML=html;
}
function renderObject(){
  if(section==='site')renderSite();
  else $('#workspace').innerHTML='<div class="edit-shell">'+Object.entries(data).map(([key,value],i)=>`<details class="section-card" data-path="${pathCode([key])}" ${i===0?'open':''}><summary>${label(key)}</summary>${tree(value,[key],key)}</details>`).join('')+'</div>';
  const box=$('#workspace');
  box.oninput=e=>{
    const code=e.target.dataset.value||e.target.dataset.lines;if(!code)return;
    const path=JSON.parse(decodeURIComponent(code));
    const value=e.target.dataset.lines!==undefined?e.target.value.split('\n').map(x=>x.trim()).filter(Boolean):e.target.type==='checkbox'?e.target.checked:e.target.type==='number'?+e.target.value:e.target.value;
    setAt(path,value);
    if(section==='site'&&path[0]==='contact_phone_display')data.contact_phone_digits=value.replace(/[^\d+]/g,'');
    if(section==='site'&&path[0]==='contact_whatsapp_display')data.contact_whatsapp_digits=value.replace(/\D/g,'');
  };
  box.onclick=e=>{
    const add=e.target.closest('[data-add]'),remove=e.target.closest('[data-remove]');
    const opened=[...box.querySelectorAll('details[open]')].map(el=>el.dataset.path).filter(Boolean);
    if(add){const array=getAt(JSON.parse(decodeURIComponent(add.dataset.add)));array.push(array.length?blank(array[0]):JSON.parse(decodeURIComponent(add.dataset.add))[0]==='committees'?{name:'',chair:''}:JSON.parse(decodeURIComponent(add.dataset.add))[0]==='past'?{term:'',name:''}:{title:'',names:[]});changed();renderObject();restoreDetails(opened,add.dataset.add)}
    if(remove&&cmsConfirm('确定删除这一项？')){const path=JSON.parse(decodeURIComponent(remove.dataset.remove));getAt(path.slice(0,-1)).splice(path.at(-1),1);changed();renderObject();restoreDetails(opened)}
  };
}
function restoreDetails(opened,added){
  if(added){const path=JSON.parse(decodeURIComponent(added));opened.push(pathCode([path[0]]),pathCode([...path,getAt(path).length-1]))}
  document.querySelectorAll('details[data-path]').forEach(el=>{el.open=opened.includes(el.dataset.path)});
}
async function upload(file,role='content',name=''){
  if(file.size>12*1024*1024)throw Error('图片请控制在 12 MB 以内');
  const base64=await readFile(file);
  const value=await api('upload',{base64,role,name});media[value.key]=value.preview.replace('/cms/media/','');return value.key;
}
async function renderMediaPage(){
  const box=$('#workspace'),isPerson=section==='people',isPDF=section==='files';
  let selector='';
  if(isPerson){
    const people=await api('people');
    selector=`<label class="field"><span>人物姓名</span><input id="media-name" list="people-names" placeholder="输入或选择网站名单中的姓名"><datalist id="people-names">${people.map(name=>`<option value="${esc(name)}">`).join('')}</datalist></label>`;
  }else if(!isPDF)selector='<label class="field"><span>图片位置</span><select id="media-role"><option value="image:hero">首页横幅</option><option value="image:chair">主席照片</option><option value="image:logo">网站标志</option><option value="image:emblem">会徽</option><option value="image:ship">帆船图片</option></select></label>';
  box.innerHTML=`<div class="edit-shell"><section class="edit-card"><h2>${labels[section]}</h2><p class="hint">${isPDF?'上传新版 PDF 后，官网的下载文件直接更新。':'选择图片后点击上传，官网直接更新。支持 JPG、PNG、WebP，最大 12 MB。'}</p><div class="media-layout"><div class="fields">${selector}<label class="field"><span>选择${isPDF?'PDF 文件':'图片'}</span><input id="media-file" type="file" accept="${isPDF?'application/pdf':'image/jpeg,image/png,image/webp'}"></label><div><button id="media-upload" class="primary">上传并更新</button></div></div><div class="current-media">${isPDF?'<a class="quiet-btn" href="/cms/media/files/membership-form.pdf" target="_blank" rel="noopener">查看当前登记表 ↗</a>':'<span class="hint">当前图片</span><img id="current-image" alt="当前图片" hidden><p id="image-empty" class="hint">选择位置或姓名后查看</p>'}</div></div></section></div>`;
  const preview=()=>{
    if(isPDF)return;
    const name=$('#media-name')?.value.trim(),role=$('#media-role')?.value;
    const key=isPerson?'people/'+name+'.webp':role==='image:chair'?(media['image:chair_custom']?'image:chair_custom':'people/容思瀚.webp'):role;
    const img=$('#current-image');img.hidden=true;$('#image-empty').hidden=false;
    if(isPerson&&!name)return;
    img.onload=()=>{img.hidden=false;$('#image-empty').hidden=true};img.onerror=()=>{$('#image-empty').textContent='暂无照片，可上传新图。'};
    img.src='/cms/media/'+encodeURI(media[key]||key)+'?v='+Date.now();
  };
  if(isPerson)$('#media-name').oninput=preview;else if(!isPDF)$('#media-role').onchange=preview;
  preview();
  $('#media-upload').onclick=()=>{
    const file=$('#media-file').files[0],name=$('#media-name')?.value.trim();
    if(!file||isPerson&&!name)return notice(isPerson?'请填写姓名并选择照片。':'请先选择文件。',true);
    working('正在上传并更新网站…',async()=>{
      if(file.size>12*1024*1024)throw Error('文件请控制在 12 MB 以内');
      if(isPDF){const base64=await readFile(file);await api('upload-pdf',{base64})}
      else await upload(file,isPerson?'person':$('#media-role').value,name||'');
      $('#media-file').value='';preview();notice(publicSite?'上传成功，官网已更新。':'上传成功，本地预览已更新。');
    });
  };
}
function readFile(file){return new Promise((resolve,reject)=>{const reader=new FileReader;reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('文件读取失败，请重新选择。'));reader.readAsDataURL(file)})}
$('#login-form').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{const value=await api('login',{account:$('#account').value.trim(),password:$('#password').value});csrf=value.csrf;$('#password').value='';await boot()}catch(err){$('#login-error').textContent=err.message}finally{button.disabled=false}};
$('#logout').onclick=async()=>{if(dirty&&!cmsConfirm('还有未保存的修改，确定退出吗？'))return;await api('logout',{});dirty=false;location.reload()};
$('#nav').onclick=e=>{const button=e.target.closest('button[data-section]');if(button)openSection(button.dataset.section)};
$('#back-list').onclick=async()=>{if(dirty){await openSection(section);return}view='list';renderCollection();scrollTo(0,0)};
$('#save').onclick=()=>working('正在保存并更新网站…',async()=>{const value=await api('data/'+section,{data,revision});revision=value.revision;dirty=false;notice(publicSite?'已保存，官网已更新。':'已保存，本地预览已更新。')});
addEventListener('beforeunload',e=>{if(dirty||busy){e.preventDefault();e.returnValue=''}});
let currentInviteId=null;
let invitationToken=new URLSearchParams(location.hash.slice(1)).get('invite');
async function start(){
  if(!invitationToken)return boot();
  $('#login').hidden=true;$('#app').hidden=true;$('#register').hidden=false;
  try{await api('invite-check',{token:invitationToken})}
  catch(err){$('#register-error').textContent=err.message;$('#register-fields').hidden=true}
}
$('#register-form').onsubmit=async e=>{
  e.preventDefault();const button=$('#register-submit');button.disabled=true;$('#register-error').textContent='';
  try{
    const value=await api('register',{token:invitationToken,phone:$('#register-phone').value.trim(),password:$('#register-password').value});
    csrf=value.csrf;$('#register-password').value='';history.replaceState(null,'','/cms/');invitationToken=null;await boot();
  }catch(err){$('#register-error').textContent=err.message}finally{button.disabled=false}
};
async function inviteList(){
  const rows=await api('invites');
  $('#invite-list').innerHTML=rows.map(row=>{
    const active=!row.registered&&!row.revoked&&row.expires*1000>Date.now();
    const status=row.registered?'已注册：'+row.registered:row.revoked?'已取消':active?'待注册':'已过期';
    return `<div class="invite-row"><span>${esc(new Date(row.created*1000).toLocaleDateString('zh-CN'))} · ${esc(status)}</span>${active?`<button data-revoke="${row.id}" type="button">取消邀请</button>`:''}</div>`;
  }).join('')||'<p class="hint">暂无邀请</p>';
}
async function createInvite(){
  const button=$('#new-invite');if(button.disabled)return;button.disabled=true;$('#copy-invite').disabled=true;$('#invite-status').textContent='正在生成…';
  try{const value=await api('invites',{});currentInviteId=value.id;$('#invite-link').value=location.origin+'/cms/#invite='+value.token;$('#copy-invite').disabled=false;$('#invite-status').textContent='链接已生成，复制后发给对方即可。';await inviteList()}
  catch(err){$('#invite-status').textContent=err.message}finally{button.disabled=false}
}
$('#invite').onclick=()=>{$('#invite-dialog').showModal();createInvite()};
$('#close-invite').onclick=()=>$('#invite-dialog').close();
$('#new-invite').onclick=createInvite;
$('#copy-invite').onclick=async()=>{
  try{await navigator.clipboard.writeText($('#invite-link').value);$('#invite-status').textContent='已复制，可以发给受邀人员。'}
  catch{$('#invite-link').focus();$('#invite-link').select();$('#invite-status').textContent='请复制已选中的链接。'}
};
$('#invite-list').onclick=async e=>{
  const button=e.target.closest('[data-revoke]');if(!button)return;button.disabled=true;
  try{await api('invites/revoke',{id:+button.dataset.revoke});if(+button.dataset.revoke===currentInviteId){$('#invite-link').value='';$('#copy-invite').disabled=true}await inviteList();$('#invite-status').textContent='邀请已取消。'}
  catch(err){button.disabled=false;$('#invite-status').textContent=err.message}
};
start().catch(err=>{$('#login-error').textContent=err.message;notice(err.message,true)});
