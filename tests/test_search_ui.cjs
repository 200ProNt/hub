const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function boot() {
  const timers = new Map();
  let timerId = 0;
  const document = {activeElement: null, addEventListener() {}, removeEventListener() {}};
  class Element {
    constructor() {
      this.children = [];
      this.dataset = {};
      this.style = {};
      this.attributes = {};
      this.handlers = {};
      this.isConnected = true;
      this.disabled = false;
      this.textContent = '';
      const classes = new Set();
      this.classList = {add: (...n) => n.forEach(v => classes.add(v)), remove: (...n) => n.forEach(v => classes.delete(v)), contains: n => classes.has(n)};
    }
    set innerHTML(html) { this.html = html; }
    get innerHTML() { return this.html || ''; }
    setAttribute(key, value) { this.attributes[key] = value; }
    removeAttribute(key) { delete this.attributes[key]; }
    addEventListener(type, fn) { this.handlers[type] = fn; }
    get offsetWidth() { return 1; }
    focus() {}
  }
  const elements = Object.fromEntries(['toolRoot', 'toolNav', 'toolTitle', 'toolHint', 'themeBtn', 'themeLabel', 'motionBtn', 'motionLabel', 'toast', 'busy', 'busyText'].map(id => [id, new Element()]));
  document.body = new Element();
  document.documentElement = new Element();
  document.createElement = () => new Element();
  document.getElementById = id => elements[id];
  document.querySelector = () => null;

  const mounted = [];
  const tools = ['a', 'b', 'c'].map(id => ({id, name: id}));
  const HubTools = {
    a: {mount(root) { mounted.push('a'); root.innerHTML = 'a'; return () => {}; }},
    b: {
      mount(root) {
        mounted.push('b');
        const pending = Hub.takeSearch('b');
        root.innerHTML = pending ? `b:${pending}` : 'b';
        return () => {};
      },
    },
    c: {
      mount(root) {
        mounted.push('c');
        Hub.setSearchHook('c', (query) => {
          root.innerHTML = `c:${query}`;
          return true;
        });
        return () => Hub.clearSearchHook('c');
      },
    },
  };
  const store = new Map();
  const context = vm.createContext({
    document,
    location: {hash: '#/a', set(value) { this.hash = value; }},
    localStorage: {getItem: (key) => (store.has(key) ? store.get(key) : null), setItem: (key, value) => store.set(key, value)},
    fetch: async () => ({ok: true, json: async () => ({tools})}),
    setTimeout(fn) { const id = ++timerId; timers.set(id, fn); return id; },
    clearTimeout(id) { timers.delete(id); },
    window: {addEventListener() {}, HubTools},
    HubTools,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8'), context);
  const Hub = vm.runInContext('Hub', context);
  Object.assign(context.window, {Hub});
  return {
    Hub, context, elements, mounted,
    run(code) { return vm.runInContext(code, context); },
    route(id) { context.location.hash = `#/${id}`; vm.runInContext('route()', context); },
    flush() { for (const [id, fn] of [...timers]) if (timers.delete(id)) fn(); },
  };
}

async function ready() {
  const app = boot();
  await new Promise((resolve) => setImmediate(resolve));
  return app;
}

test('searchIn opens another tool and hands it the query', async () => {
  const app = await ready();
  app.run("Hub.searchIn('b','корм')");
  app.route('b');
  app.flush();
  assert.equal(app.elements.toolRoot.innerHTML, 'b:корм');
  assert.deepEqual(app.mounted, ['a', 'b']);
  assert.equal(app.Hub.pendingSearch, null);
});

test('searchIn on the open tool uses its hook instead of remounting', async () => {
  const app = await ready();
  app.route('c');
  app.flush();
  app.run("Hub.searchIn('c','иголка')");
  assert.equal(app.elements.toolRoot.innerHTML, 'c:иголка');
  assert.deepEqual(app.mounted, ['a', 'c']);
});

test('the open tool without a hook still receives the query on remount', async () => {
  const app = await ready();
  app.run("Hub.searchIn('a','xyz')");
  assert.equal(app.elements.toolRoot.innerHTML, 'a');
  assert.equal(app.Hub.pendingSearch, null);
});

test('a stale pending query is dropped by another tool', async () => {
  const app = await ready();
  app.run("Hub.pendingSearch = {tool: 'zzz', query: 'x'}");
  app.route('b');
  app.flush();
  assert.equal(app.elements.toolRoot.innerHTML, 'b');
  assert.equal(app.Hub.pendingSearch, null);
});

test('hooks are cleared when the tool is left', async () => {
  const app = await ready();
  app.route('c');
  app.flush();
  app.route('a');
  app.flush();
  assert.deepEqual(Object.keys(app.Hub.searchHooks), []);
});
