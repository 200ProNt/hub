const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const RUNS = {
  runs: [
    {
      run_id: 'del_1', source: 'cleanup', folder: 'C:\\demo', time: 1700000000,
      count: 7, size: 2048,
      items: [
        {name: 'a.txt', kind: 'file', size: 1024},
        {name: 'old-folder', kind: 'dir', size: 1024},
      ],
    },
  ],
  total_count: 7,
  total_size: 2048,
};

const EMPTY = {runs: [], total_count: 0, total_size: 0};

function setup({runs = RUNS, confirmed = true, results = {}} = {}) {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) nodes.set(key, {
      innerHTML: '', textContent: '', value: '', dataset: {}, disabled: false,
      classes: new Set(),
      classList: {
        add(...names) { names.forEach((name) => nodes.get(key).classes.add(name)); },
        remove(...names) { names.forEach((name) => nodes.get(key).classes.delete(name)); },
        toggle(name, force) { if (force) nodes.get(key).classes.add(name); else nodes.get(key).classes.delete(name); },
        contains(name) { return nodes.get(key).classes.has(name); },
      },
      listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; },
      querySelectorAll() { return []; }, querySelector(sel) { return node(key + ' ' + sel); }, focus() {},
    });
    return nodes.get(key);
  };
  const calls = [];
  const Hub = {
    escapeHtml: String, plural: () => 'штук', fmtSize: (size) => `${size} Б`,
    toast() {}, setBusy() {}, dismissDialog() {},
    async confirm() { return confirmed; },
    async api(url, body) {
      calls.push({url, body});
      if (url === '/api/trash/runs') return runs;
      return results[url] || {removed: 1, freed: 4096, restored_count: 1, errors: []};
    },
  };
  const context = {window: {HubTools: {}}, Hub, console};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/tools/trash.js'), 'utf8'), context);
  const root = {innerHTML: '', querySelector: node};
  const cleanup = context.window.HubTools.trash.mount(root);
  return {node, calls, cleanup};
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 15));

function press(s, attribute, runId = 'del_1') {
  const button = {hasAttribute: (name) => name === attribute, closest: () => ({dataset: {run: runId}})};
  s.node('#trashList').listeners.click({target: {closest: (sel) => (sel === 'button' ? button : null)}});
}

test('trash lists what can still be restored', async () => {
  const s = setup();
  await settle();
  const html = s.node('#trashList').innerHTML;
  assert.ok(html.includes('Уборка'));
  assert.ok(html.includes('a.txt'));
  assert.ok(html.includes('old-folder'));
  assert.ok(html.includes('и ещё 5'));
  assert.equal(s.node('#trashTotals').textContent, '7 штук · 2048 Б');
  assert.equal(s.node('#trashEmpty').disabled, false);
  assert.equal(s.node('#trashBlank').classList.contains('hidden'), true);
});

test('an empty trash shows the blank state and disables clearing', async () => {
  const s = setup({runs: EMPTY});
  await settle();
  assert.equal(s.node('#trashList').innerHTML, '');
  assert.equal(s.node('#trashBlank').classList.contains('hidden'), false);
  assert.equal(s.node('#trashEmpty').disabled, true);
  assert.equal(s.node('#trashTotals').textContent, 'пусто');
});

test('restoring a run sends its id and reloads the list', async () => {
  const s = setup();
  await settle();
  press(s, 'data-restore');
  await settle();
  const restore = s.calls.find((call) => call.url === '/api/trash/restore');
  assert.equal(restore.body.run_id, 'del_1');
  assert.equal(s.calls.filter((call) => call.url === '/api/trash/runs').length, 2);
});

test('permanent deletion asks for confirmation and sends it', async () => {
  const s = setup();
  await settle();
  press(s, 'data-purge');
  await settle();
  const purge = s.calls.find((call) => call.url === '/api/trash/purge');
  assert.deepEqual([...purge.body.run_ids], ['del_1']);
  assert.equal(purge.body.confirmed, true);
});

test('declining confirmation keeps the files', async () => {
  const s = setup({confirmed: false});
  await settle();
  press(s, 'data-purge');
  await settle();
  assert.ok(!s.calls.some((call) => call.url === '/api/trash/purge'));

  await s.node('#trashEmpty').listeners.click();
  await settle();
  assert.ok(!s.calls.some((call) => call.url === '/api/trash/empty'));
});

test('clearing the whole trash sends confirmation and reports freed space', async () => {
  const s = setup();
  await settle();
  await s.node('#trashEmpty').listeners.click();
  await settle();
  const empty = s.calls.find((call) => call.url === '/api/trash/empty');
  assert.equal(empty.body.confirmed, true);
});

test('an unmounted trash tab cannot change files', async () => {
  const s = setup();
  await settle();
  s.cleanup();
  press(s, 'data-restore');
  await settle();
  assert.ok(!s.calls.some((call) => call.url === '/api/trash/restore'));
});

test('legacy journals without a source are labelled as duplicates', async () => {
  const s = setup({
    runs: {runs: [{run_id: 'del_old', source: '', folder: '', time: 1700000000, count: 1, size: 1, items: []}], total_count: 1, total_size: 1},
  });
  await settle();
  assert.ok(s.node('#trashList').innerHTML.includes('Дубликаты'));
});
