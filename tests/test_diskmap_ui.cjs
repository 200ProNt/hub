const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function setup(choices = ['trash'], confirmed = true) {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) nodes.set(key, {
      innerHTML: '', textContent: '', value: '', dataset: {}, disabled: false,
      classList: {add(){},remove(){},toggle(){}},
      listeners: {}, addEventListener(type,fn){this.listeners[type]=fn;},
      querySelectorAll(){return [];}, querySelector(sel){return node(key+' '+sel);}, focus(){},
    });
    return nodes.get(key);
  };
  const calls = [];
  const file = {name:'unused.txt',path:'C:\\demo\\unused.txt',size:24};
  const Hub = {
    defaultFolder:'C:\\demo',escapeHtml:String,plural:()=> 'файлов',fmtSize:String,
    toast(){},setBusy(){},dismissDialog(){},
    async choose(){return choices.shift() ?? null;}, async confirm(){return confirmed;},
    async api(url,body){
      calls.push({url,body});
      if(url.endsWith('/last-run')) return {last_run:null};
      if(url.endsWith('/files')) return {folder:'C:\\demo',files:[file],errors:[],truncated:false};
      if(url.endsWith('/scan')) return {folder:'C:\\demo',name:'demo',entries:[{kind:'files',path:'C:\\demo',name:'Файлы',size:24,count:1}],total:24,dirs:0,files:1,seconds:0,links:0,errors:[]};
      if(url.endsWith('/remove')) return {run_id:'test',removed_count:1,removed_size:24,errors:[]};
      return {restored_count:1,errors:[]};
    },
  };
  const context = {window:{HubTools:{}},Hub,console};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/tools/diskmap.js'),'utf8'),context);
  const root = {innerHTML:'', querySelector:node};
  const cleanup = context.window.HubTools.diskmap.mount(root);
  return {node,calls,cleanup};
}
async function openFiles(s) {
  await s.node('#diskScan').listeners.click();
  await s.node('#diskLegend').listeners.click({target:{closest:()=>({dataset:{i:'0'}})}});
}
test('file entry opens inline list instead of Explorer',async()=>{
  const s=setup(); await openFiles(s);
  assert.ok(s.calls.some(x=>x.url==='/api/diskmap/files'));
  assert.ok(s.node('#diskFileList').innerHTML.includes('unused.txt'));
});
test('trash choice sends trash mode and shows undo',async()=>{
  const s=setup(); await openFiles(s);
  await s.node('#diskFileList').listeners.click({target:{closest:()=>({dataset:{delete:'0'}})}});
  const request=s.calls.find(x=>x.url==='/api/diskmap/remove');
  assert.equal(request?.body.mode,'trash');
  assert.ok(s.node('#diskUndo').innerHTML.includes('Вернуть'));
});
test('cancel does not remove a file',async()=>{
  const s=setup([null]); await openFiles(s);
  await s.node('#diskFileList').listeners.click({target:{closest:()=>({dataset:{delete:'0'}})}});
  assert.ok(!s.calls.some(x=>x.url.endsWith('/remove')));
});
test('permanent removal sends explicit confirmation',async()=>{
  const s=setup(['delete']); await openFiles(s);
  await s.node('#diskFileList').listeners.click({target:{closest:()=>({dataset:{delete:'0'}})}});
  const request=s.calls.find(x=>x.url.endsWith('/remove'));
  assert.equal(request?.body.mode,'delete');
  assert.equal(request?.body.confirmed,true);
});
test('declining permanent confirmation preserves file',async()=>{
  const s=setup(['delete'],false); await openFiles(s);
  await s.node('#diskFileList').listeners.click({target:{closest:()=>({dataset:{delete:'0'}})}});
  assert.ok(!s.calls.some(x=>x.url.endsWith('/remove')));
});
test('undo posts run id and reloads map and files',async()=>{
  const s=setup(); await openFiles(s);
  await s.node('#diskFileList').listeners.click({target:{closest:()=>({dataset:{delete:'0'}})}});
  await s.node('#diskUndo').listeners.click({target:{closest:()=>({})}});
  assert.equal(s.calls.find(x=>x.url.endsWith('/undo'))?.body.run_id,'test');
  assert.equal(s.calls.filter(x=>x.url.endsWith('/scan')).length,3);
});
test('unmounted tool cannot delete files',async()=>{
  const s=setup(); await openFiles(s); s.cleanup();
  await s.node('#diskFileList').listeners.click({target:{closest:()=>({dataset:{delete:'0'}})}});
  assert.ok(!s.calls.some(x=>x.url.endsWith('/remove')));
});
