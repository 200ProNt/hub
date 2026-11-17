const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const SCAN = {
  folder: 'C:\\demo',
  age_days: 365,
  old: [{name: 'old.txt', path: 'C:\\demo\\old.txt', size: 100, modified: 0, kind: 'file', reason: 'old'}],
  junk: [{name: 'cache.tmp', path: 'C:\\demo\\cache.tmp', size: 10, modified: 0, kind: 'file', reason: 'junk'}],
  empty: [{name: 'empty', path: 'C:\\demo\\empty', size: 0, kind: 'dir'}],
  old_size: 100,
  junk_size: 10,
  empty_size: 0,
  scanned: 2,
  links: 0,
  errors: [],
  truncated: false,
  seconds: 0.1,
};

function setup(choices = ['trash'], confirmed = true) {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) nodes.set(key, {
      innerHTML: '', textContent: '', value: '', dataset: {}, disabled: false, checked: false,
      classList: {add(){},remove(){},toggle(){}},
      listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; },
      querySelectorAll() { return []; }, querySelector(sel) { return node(key + ' ' + sel); }, focus() {},
    });
    return nodes.get(key);
  };
  const calls = [];
  const Hub = {
    defaultFolder: 'C:\\demo', escapeHtml: String, plural: () => 'штук', fmtSize: String,
    toast() {}, setBusy() {}, dismissDialog() {},
    async choose() { return choices.shift() ?? null; }, async confirm() { return confirmed; },
    async api(url, body) {
      calls.push({url, body});
      if (url.endsWith('/last-run')) return {last_run: null};
      if (url.endsWith('/scan')) return SCAN;
      if (url.endsWith('/remove')) return {run_id: 'test', removed_count: 1, removed_size: 110, errors: []};
      return {restored_count: 1, errors: []};
    },
  };
  const context = {window: {HubTools: {}}, Hub, console};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/tools/cleanup.js'), 'utf8'), context);
  const root = {innerHTML: '', querySelector: node};
  const cleanup = context.window.HubTools.cleanup.mount(root);
  return {node, calls, cleanup};
}

async function scan(s) {
  await s.node('#cleanScan').listeners.click();
}

function pick(s, path = 'C:\\demo\\old.txt') {
  s.node('#cleanList').listeners.change({
    target: {checked: true, closest: () => ({dataset: {path}, classList: {toggle() {}}})},
  });
}

test('scan shows old files and enables selection', async () => {
  const s = setup();
  await scan(s);
  assert.ok(s.node('#cleanList').innerHTML.includes('old.txt'));
  assert.equal(s.node('#cleanSelCount').textContent, '0');
  pick(s);
  assert.equal(s.node('#cleanSelCount').textContent, '1');
  assert.equal(s.node('#cleanRemove').disabled, false);
});

test('remove sends the selected paths to the trash', async () => {
  const s = setup();
  await scan(s);
  pick(s);
  await s.node('#cleanRemove').listeners.click();
  const request = s.calls.find((call) => call.url === '/api/cleanup/remove');
  assert.deepEqual([...request.body.paths], ['C:\\demo\\old.txt']);
  assert.equal(request.body.mode, 'trash');
  assert.ok(s.node('#cleanUndo').innerHTML.includes('Вернуть'));
});

test('cancel keeps everything in place', async () => {
  const s = setup([null]);
  await scan(s);
  pick(s);
  await s.node('#cleanRemove').listeners.click();
  assert.ok(!s.calls.some((call) => call.url.endsWith('/remove')));
});

test('permanent removal asks twice and sends confirmation', async () => {
  const s = setup(['delete']);
  await scan(s);
  pick(s);
  await s.node('#cleanRemove').listeners.click();
  const request = s.calls.find((call) => call.url.endsWith('/remove'));
  assert.equal(request.body.mode, 'delete');
  assert.equal(request.body.confirmed, true);
});

test('declining the second confirmation changes nothing', async () => {
  const s = setup(['delete'], false);
  await scan(s);
  pick(s);
  await s.node('#cleanRemove').listeners.click();
  assert.ok(!s.calls.some((call) => call.url.endsWith('/remove')));
});

test('mark all selects the visible group', async () => {
  const s = setup();
  await scan(s);
  await s.node('#cleanMarkAll').listeners.click();
  assert.equal(s.node('#cleanSelCount').textContent, '1');
  pick(s, 'C:\\demo\\empty');
  assert.equal(s.node('#cleanSelCount').textContent, '2');
});

test('undo returns the run and rescans', async () => {
  const s = setup();
  await scan(s);
  pick(s);
  await s.node('#cleanRemove').listeners.click();
  await s.node('#cleanUndo').listeners.click({target: {closest: () => ({})}});
  assert.equal(s.calls.find((call) => call.url.endsWith('/undo'))?.body.run_id, 'test');
  assert.equal(s.calls.filter((call) => call.url.endsWith('/scan')).length, 2);
});

test('unmounted tool cannot remove anything', async () => {
  const s = setup();
  await scan(s);
  pick(s);
  s.cleanup();
  await s.node('#cleanRemove').listeners.click();
  assert.ok(!s.calls.some((call) => call.url.endsWith('/remove')));
});
