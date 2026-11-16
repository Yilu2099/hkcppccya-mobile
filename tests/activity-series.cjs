// Dependency-free checks against the actual editor and frontend source.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'admin/static/admin.js'), 'utf8');
new Function(source);
const prefix = source.slice(0, source.indexOf('async function upload'));
const elements = {};
const element = key => elements[key] ??= {innerHTML:'', classList:{toggle(){}}, setAttribute(){}, querySelectorAll(){return []}};
const document = {querySelector:element, querySelectorAll:()=>[]};
const editor = new Function('document', 'cmsSearchText', prefix + `
return {
  setup(rows, brands){section='news';view='editor';data=rows;selected=0;seriesBrands=brands;},
  html(){renderEditor();return $('#workspace').innerHTML;},
  clear(){ $('#workspace').oninput({target:{dataset:{field:'tag'},value:''}});return data[0].tag;},
  site(brands){section='site';data={brands,sails:[]};renderSite();return $('#workspace').innerHTML;},
  rowInfo
};
`)(document, value=>value);
const brands = {tour:{tag:'旅學團',name:'旅學團'},national:{tag:'國情班',name:'國情班'},policy:{tag:'政情班',name:'政情班'},mentor:{tag:'青年導師',name:'青年導師計劃'}};
const row = {id:1084, title:'Test', date:'2026-11-16', body:[], images:[], category:'news', tag:'tour'};
editor.setup([row], brands);
let html=editor.html();
assert.ok(html.indexOf('data-field="tag"') < html.indexOf('文章正文'));
assert.equal(html.split('data-field="tag"').length, 2);
assert.ok(html.includes('<option value="">不显示标签</option>'));
assert.ok(html.includes('value="tour" selected'));
assert.equal(editor.clear(), '');
assert.ok(!editor.html().includes('value="tour" selected'));
brands.mentor.tag='新名稱 <測試>';
editor.setup([{...row,tag:'mentor'}], brands);
assert.ok(editor.html().includes('新名稱 &lt;測試&gt;'));
assert.ok(editor.rowInfo({tag:'mentor'}).includes('新名稱'));
html=editor.site(brands);
assert.ok(html.indexOf('活动系列与标签名称') < html.indexOf('首页'));
assert.ok(html.includes('标签文字（日期旁）'));
const template=fs.readFileSync(path.join(root, 'src/index.template.html'), 'utf8');
const lines=template.split('\n');
const mapping=lines.find(line=>line.startsWith('const NEWS_TAG='));
const chip=lines.find(line=>line.startsWith('const tagChip='));
const render=new Function('NEWS', 'BRANDS', 'esc', mapping+'\n'+chip+'\nreturn tagChip;');
const escape=value=>String(value).replace(/</g,'&lt;').replace(/>/g,'&gt;');
for (const id of [1082,1084,1085,1086,1087,1088]) assert.equal(render([{id,tag:''}],brands,escape)({id}), '');
assert.ok(render([{id:1084,tag:'mentor'}],brands,escape)({id:1084}).includes('新名稱 &lt;測試&gt;'));
assert.equal(render([{id:1084}],brands,escape)({id:1084}), '');
assert.equal(render([{id:999,tag:'unknown'}],brands,escape)({id:999}), '');
console.log('Activity series editor and frontend checks passed.');
