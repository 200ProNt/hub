const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const TOOLS = [
  {id: 'notes', name: 'Заметки', hint: 'Быстрые записи на этом компьютере'},
  {id: 'trash', name: 'Корзина', hint: 'Что можно вернуть на место'},
];

const SEARCH = {
  tools: [],
  notes: [{id: 'n1', title: 'Корм коту', snippet: 'купить корм и молоко'}],
  clipboard: [{id: 'c1', snippet: '…корм для кота…', pinned: false}],
};

class El {
  constructor() {
    this.children = [];
    this.handlers = {};
    this.dataset = {};
    this.attributes = {};
    this.value = '';
    this.id = '';
    this.focused = false;
    this.isConnected = true;
    this.classes = new Set();
    const self = this;
    this.classList = {
      add: (...names) => names.forEach((name) => self.classes.add(name)),
      remove: (...names) => names.forEach((name) => self.classes.delete(name)),
      toggle: (name, force) => {
        if (force) self.classes.add(name);
        else self.classes.delete(name);
      },
      contains: (name) => self.classes.has(name),
    };
  }

  set className(value) {
    this.classNameValue = value;
    this.classes = new Set(String(value).split(/\s+/).filter(Boolean));
  }

  get className() {
    return this.classNameValue || '';
  }

  set innerHTML(html) {
    this.html = html;
    this.children = [...String(html).matchAll(/<(\w+)[^>]*\bid="([^"]+)"[^>]*>/g)].map(([, tag, id]) => {
      const child = new El();
      child.tag = tag;
      child.id = id;
      return child;
    });
  }

  get innerHTML() {
    return this.html || '';
  }

  addEventListener(type, fn) { this.handlers[type] = fn; }
  setAttribute(key, value) { this.attributes[key] = value; }
  removeAttribute(key) { delete this.attributes[key]; }
  hasAttribute(key) { return key in this.attributes; }
  appendChild(child) { this.children.push(child); this.bodyChild = child; }
  focus() { this.focused = true; document.activeElement = this; }
  scrollIntoView() {}

  querySelector(selector) {
    if (selector.startsWith('#')) return this.children.find((child) => child.id === selector.slice(1)) || null;
    return this.children[0] || null;
  }

  querySelectorAll() { return []; }
}

let document;

function setup(search = SEARCH) {
  document = new El();
  document.body = new El();
  document.activeElement = null;
  const listeners = new Map();
  document.addEventListener = (type, fn) => listeners.set(type, fn);
  document.removeEventListener = (type) => listeners.delete(type);
  document.createElement = () => new El();

  const calls = [];
  const searches = [];
  const Hub = {
    tools: TOOLS,
    escapeHtml: (value) => String(value).replace(/[&<>"']/g, (char) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char])),
    toast() {},
    async api(url) {
      calls.push(url);
      return search;
    },
    searchIn(toolId, query) { searches.push({toolId, query}); return true; },
  };
  const context = {window: {}, Hub, document, location: {hash: '#/notes'}, setTimeout, clearTimeout, encodeURIComponent, console};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/palette.js'), 'utf8'), context);
  context.window.HubPalette.init();
  return {
    palette: context.window.HubPalette,
    calls, searches, listeners,
    overlay: document.body.children[0],
    input() { return document.body.children[0].querySelector('#paletteInput'); },
    list() { return document.body.children[0].querySelector('#paletteList'); },
    key(key, extras = {}) {
      let prevented = false;
      listeners.get('keydown')?.({key, preventDefault() { prevented = true; }, ...extras});
      return prevented;
    },
  };
}

const wait = (ms = 160) => new Promise((resolve) => setTimeout(resolve, ms));

test('ctrl+k opens the palette with every tool and closes on a second press', () => {
  const s = setup();
  assert.equal(s.overlay.classList.contains('hidden'), true);
  assert.equal(s.key('k', {ctrlKey: true}), true);
  assert.equal(s.overlay.classList.contains('hidden'), false);
  assert.equal(s.input().focused, true);
  assert.ok(s.list().innerHTML.includes('Заметки'));
  assert.ok(s.list().innerHTML.includes('Корзина'));

  s.key('k', {ctrlKey: true});
  assert.equal(s.overlay.classList.contains('hidden'), true);
});

test('typing searches tools, notes and the clipboard through the server', async () => {
  const s = setup();
  s.key('k', {ctrlKey: true});
  s.input().value = 'корм';
  s.input().handlers.input();
  await wait();
  const html = s.list().innerHTML;
  assert.ok(s.calls.includes('/api/search?q=%D0%BA%D0%BE%D1%80%D0%BC'));
  assert.ok(html.includes('Заметки'));
  assert.ok(html.includes('Корм коту'));
  assert.ok(html.includes('Буфер обмена'));
  assert.ok(html.includes('корм для кота'));
});

test('enter opens a note with the same query', async () => {
  const s = setup();
  s.key('k', {ctrlKey: true});
  s.input().value = 'корм';
  s.input().handlers.input();
  await wait();
  s.input().handlers.keydown({key: 'Enter', preventDefault() {}});
  assert.deepEqual([...s.searches], [{toolId: 'notes', query: 'корм'}]);
  assert.equal(s.overlay.classList.contains('hidden'), true);
});

test('arrow keys move the active result', async () => {
  const s = setup();
  s.key('k', {ctrlKey: true});
  s.input().value = 'корм';
  s.input().handlers.input();
  await wait();
  s.input().handlers.keydown({key: 'ArrowDown', preventDefault() {}});
  s.input().handlers.keydown({key: 'Enter', preventDefault() {}});
  assert.equal(s.searches[0].toolId, 'clipboard');
});

test('escape closes without opening anything', () => {
  const s = setup();
  s.key('k', {ctrlKey: true});
  assert.equal(s.key('Escape'), true);
  assert.equal(s.overlay.classList.contains('hidden'), true);
  assert.equal(s.searches.length, 0);
});

test('an empty search shows all tools without a request', async () => {
  const s = setup();
  s.key('k', {ctrlKey: true});
  s.input().value = '';
  s.input().handlers.input();
  await wait(10);
  assert.equal(s.calls.length, 0);
  assert.ok(s.list().innerHTML.includes('Заметки'));
  assert.ok(s.list().innerHTML.includes('Корзина'));
});

test('search results escape untrusted titles', async () => {
  const s = setup({tools: [], notes: [{id: 'n1', title: '<script>alert(1)</script>', snippet: '<b>'}], clipboard: []});
  s.key('k', {ctrlKey: true});
  s.input().value = 'x';
  s.input().handlers.input();
  await wait();
  assert.ok(!s.list().innerHTML.includes('<script'));
  assert.ok(s.list().innerHTML.includes('&lt;script'));
});
