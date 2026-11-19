const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const NOTES = [
  {
    id: 'note_1',
    title: 'Список покупок #дела',
    text: '- [ ] Молоко\n- [x] Хлеб\n#еда',
    pinned: false,
    created: 1700000000,
    updated: 1700000000,
    chars: 30,
    tags: ['дела', 'еда'],
  },
];

function setup() {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) {
      nodes.set(key, {
        innerHTML: '',
        textContent: '',
        value: '',
        dataset: {},
        disabled: false,
        classList: {
          classes: new Set(),
          add(c) { this.classes.add(c); },
          remove(c) { this.classes.delete(c); },
          toggle(c, v) { if (v) this.classes.add(c); else this.classes.delete(c); },
          contains(c) { return this.classes.has(c); },
        },
        listeners: {},
        addEventListener(type, fn) { this.listeners[type] = fn; },
        querySelectorAll() { return []; },
        querySelector(sel) { return node(key + ' ' + sel); },
        focus() {},
        scrollIntoView() {},
      });
    }
    return nodes.get(key);
  };

  const calls = [];
  const Hub = {
    defaultFolder: 'C:\\demo',
    escapeHtml: (s) => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
    plural: () => 'символов',
    toast(m) { calls.push({ type: 'toast', message: m }); },
    setBusy() {},
    dismissDialog() {},
    setSearchHook() {},
    takeSearch: () => '',
    clearSearchHook() {},
    async api(url, body) {
      calls.push({ type: 'api', url, body });
      if (url === '/api/notes/items') return { items: NOTES, total: NOTES.length };
      if (url === '/api/notes/update') return { item: { ...NOTES[0], text: body.text } };
      return {};
    },
  };

  const context = {
    window: {
      HubTools: {},
      addEventListener() {},
      removeEventListener() {},
    },
    Hub,
    console,
  };

  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/tools/notes.js'), 'utf8'), context);
  const root = { innerHTML: '', querySelector: node };
  const cleanup = context.window.HubTools.notes.mount(root);
  return { node, calls, cleanup, context };
}

test('notes tool mounts and registers in HubTools', () => {
  const { node, cleanup, context } = setup();
  assert.ok(context.window.HubTools.notes);
  assert.equal(typeof context.window.HubTools.notes.mount, 'function');
  assert.ok(node('#notesGrid'));
  assert.ok(node('#notesTagsBar'));
  assert.equal(typeof cleanup, 'function');
  cleanup();
});
