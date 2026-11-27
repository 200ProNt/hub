const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function setup(choices = ['trash'], confirmed = true, jobApi = null) {
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
  const calls = [], toasts = [];
  const file = {name:'unused.txt',path:'C:\\demo\\unused.txt',size:24};
  const Hub = {
    defaultFolder:'C:\\demo',escapeHtml:String,plural:()=> 'файлов',fmtSize:String,
    diskmapJobs: Boolean(jobApi),
    toast(message){toasts.push(message);},setBusy(){},dismissDialog(){},
    async choose(){return choices.shift() ?? null;}, async confirm(){return confirmed;},
    async api(url,body){
      calls.push({url,body});
      if(url.includes('/jobs/')) return jobApi(url, body);
      if(url.endsWith('/last-run')) return {last_run:null};
      if(url.endsWith('/files')) return {folder:'C:\\demo',files:[file],errors:[],truncated:false};
      if(url.endsWith('/scan')) return {folder:'C:\\demo',name:'demo',entries:[{kind:'files',path:'C:\\demo',name:'Файлы',size:24,count:1}],total:24,dirs:0,files:1,seconds:0,links:0,errors:[]};
      if(url.endsWith('/remove')) return {run_id:'test',removed_count:1,removed_size:24,errors:[]};
      return {restored_count:1,errors:[]};
    },
  };
  const context = {window:{HubTools:{}},Hub,console,setTimeout};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/tools/diskmap.js'),'utf8'),context);
  const root = {innerHTML:'', querySelector:node};
  const cleanup = context.window.HubTools.diskmap.mount(root);
  return {node,calls,cleanup,toasts};
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
test('progress is shown and a failed cancel request does not renew the job lease', async () => {
  const s = setup([], true, async (url) => {
    if (url.endsWith('/start')) return {id: 'scan'};
    if (url.endsWith('/status')) return {state: 'running', entries: 64, files: 63, bytes: 128};
    throw new Error('connection lost');
  });
  const scan = s.node('#diskScan').listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.match(s.node('#diskProgress').textContent, /64.*63.*128/);
  s.node('#diskCancel').listeners.click();
  await scan;
  const calls = s.calls.filter(x => x.url.includes('/jobs/'));
  assert.deepEqual(calls.map(x => x.url.split('/').pop()), ['start', 'status', 'cancel']);
  assert.equal(calls.at(-1).body.id, 'scan');
});
test('leaving the disk map cancels a job whose start response is pending', async () => {
  let started;
  const s = setup([], true, async (url) => {
    if (url.endsWith('/start')) return new Promise(resolve => { started = resolve; });
    assert.ok(url.endsWith('/cancel'));
    return {state: 'cancelling'};
  });
  const scan = s.node('#diskScan').listeners.click();
  s.cleanup();
  started({id: 'late-job'});
  await scan;
  const calls = s.calls.filter(x => x.url.includes('/jobs/'));
  assert.deepEqual(calls.map(x => x.url.split('/').pop()), ['start', 'cancel']);
  assert.equal(calls.at(-1).body.id, 'late-job');
});
test('browser reports a completed cancellation only after the terminal state', async () => {
  let stopped = false;
  const s = setup([], true, async (url) => {
    if (url.endsWith('/start')) return { id: 'scan' };
    if (url.endsWith('/cancel')) return { state: 'cancelling' };
    if (stopped) return { state: 'cancelled' };
    return { state: 'running', entries: 0, files: 0, bytes: 0 };
  });
  const scan = s.node('#diskScan').listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  s.node('#diskCancel').listeners.click();
  assert.ok(!s.toasts.some(message => message.includes('отменён')));
  stopped = true;
  await scan;
  assert.ok(s.toasts.some(message => message.includes('отменён')));
});
