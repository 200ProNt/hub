const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const SCAN = {
  folder: 'C:\\demo',
  files: [{name: 'huge.bin', path: 'C:\\demo\\huge.bin', size: 2048, modified: 0, folder: 'C:\\demo'}],
  matched: 1,
  matched_size: 2048,
  scanned: 3,
  min_size: 20 * 1024 * 1024,
  limit: 100,
  links: 0,
  errors: [],
  truncated: false,
  seconds: 0.1,
};

function setup(choices = ['trash'], confirmed = true) {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) nodes.set(key, {
      innerHTML: '', textContent: '', value: '', dataset: {}, disabled: false,
      classList: {add(){},remove(){},toggle(){}},
      listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; },
      querySelectorAll() { return []; }, querySelector(sel) { return node(key + ' ' + sel); }, focus() {},
    });
    return nodes.get(key);
  };
  const calls = [];
  const Hub = {
    defaultFolder: 'C:\\demo', escapeHtml: String, plural: () => 'файлов', fmtSize: String,
    toast() {}, setBusy() {}, dismissDialog() {},
    async choose() { return choices.shift() ?? null; }, async confirm() { return confirmed; },
    async api(url, body) {
      calls.push({url, body});
      if (url.endsWith('/last-run')) return {last_run: null};
      if (url.endsWith('/scan')) return SCAN;
      if (url.endsWith('/remove')) return {run_id: 'test', removed_count: 1, removed_size: 2048, errors: []};
      return {restored_count: 1, errors: []};
    },
  };
  const context = {window: {HubTools: {}}, Hub, console};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/tools/bigfiles.js'), 'utf8'), context);
  const root = {innerHTML: '', querySelector: node};
  const cleanup = context.window.HubTools.bigfiles.mount(root);
  return {node, calls, cleanup};
}

function clickDelete(act = 'delete') {
  const card = {dataset: {index: '0'}};
  const button = {dataset: {act}, closest: () => card};
  return {target: {closest: () => button}};
}

test('scan lists the biggest file', async () => {
  const s = setup();
  await s.node('#bigScan').listeners.click();
  assert.ok(s.node('#bigList').innerHTML.includes('huge.bin'));
  assert.ok(s.calls.some((call) => call.url === '/api/bigfiles/scan'));
});

test('trash choice sends trash mode and shows undo', async () => {
  const s = setup();
  await s.node('#bigScan').listeners.click();
  await s.node('#bigList').listeners.click(clickDelete());
  const request = s.calls.find((call) => call.url === '/api/bigfiles/remove');
  assert.equal(request.body.mode, 'trash');
  assert.equal(request.body.confirmed, false);
  assert.ok(s.node('#bigUndo').innerHTML.includes('Вернуть'));
});

test('cancel does not remove the file', async () => {
  const s = setup([null]);
  await s.node('#bigScan').listeners.click();
  await s.node('#bigList').listeners.click(clickDelete());
  assert.ok(!s.calls.some((call) => call.url.endsWith('/remove')));
});

test('permanent removal sends explicit confirmation', async () => {
  const s = setup(['delete']);
  await s.node('#bigScan').listeners.click();
  await s.node('#bigList').listeners.click(clickDelete());
  const request = s.calls.find((call) => call.url.endsWith('/remove'));
  assert.equal(request.body.mode, 'delete');
  assert.equal(request.body.confirmed, true);
});

test('declining permanent confirmation preserves the file', async () => {
  const s = setup(['delete'], false);
  await s.node('#bigScan').listeners.click();
  await s.node('#bigList').listeners.click(clickDelete());
  assert.ok(!s.calls.some((call) => call.url.endsWith('/remove')));
});

test('unmounted tool cannot remove files', async () => {
  const s = setup();
  await s.node('#bigScan').listeners.click();
  s.cleanup();
  await s.node('#bigList').listeners.click(clickDelete());
  assert.ok(!s.calls.some((call) => call.url.endsWith('/remove')));
});
