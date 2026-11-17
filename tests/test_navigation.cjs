const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function boot(reduced = false) {
  const timers = new Map();
  let timerId = 0;
  const listeners = new Map();
  const document = {
    activeElement: null,
    addEventListener(type, fn) { listeners.set(type, fn); },
    removeEventListener(type, fn) { if (listeners.get(type) === fn) listeners.delete(type); },
  };
  class Element {
    constructor() {
      this.children = [];
      this.dataset = {};
      this.style = {};
      this.attributes = {};
      this.handlers = {};
      this.isConnected = true;
      this.disabled = false;
      const classes = new Set();
      this.classList = { add: (...names) => names.forEach(n => classes.add(n)), remove: (...names) => names.forEach(n => classes.delete(n)), contains: n => classes.has(n) };
    }
    set innerHTML(html) {
      this.html = html;
      this.children = [...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].map(match => {
        const button = new Element();
        for (const [, key, value] of match[1].matchAll(/data-([\w-]+)="([^"]*)"/g)) button.dataset[key] = value;
        button.className = /class="([^"]*)"/.exec(match[1])?.[1] || '';
        return button;
      });
    }
    get innerHTML() { return this.html || ''; }
    setAttribute(key, value) { this.attributes[key] = value; }
    removeAttribute(key) { delete this.attributes[key]; }
    addEventListener(type, fn) { this.handlers[type] = fn; }
    appendChild(child) { this.children.push(child); child.parent = this; }
    querySelectorAll() { return this.children; }
    querySelector(selector) {
      const data = /data-(act|choice)="([^"]+)"/.exec(selector);
      return data ? this.children.find(child => child.dataset[data[1]] === data[2]) : this.children[0];
    }
    closest() { return this; }
    contains(node) { return node === this || this.children.includes(node); }
    focus() { document.activeElement = this; }
    remove() { this.isConnected = false; if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this); }
    click(target = this) { this.handlers.click?.({ target }); }
  }
  const elements = Object.fromEntries(['toolRoot', 'toolNav', 'toolTitle', 'toolHint', 'themeBtn', 'themeLabel', 'motionBtn', 'motionLabel', 'toast', 'busy', 'busyText'].map(id => [id, new Element()]));
  const shell = new Element();
  document.body = new Element();
  document.documentElement = new Element();
  document.createElement = () => new Element();
  document.getElementById = id => elements[id];
  document.querySelector = selector => selector === '.shell' ? shell : null;
  const mounted = [];
  const cleaned = [];
  const store = new Map();
  const tools = ['a', 'b', 'c'].map(id => ({ id, name: id }));
  const context = vm.createContext({
    document,
    location: { hash: '#/a' },
    localStorage: { getItem(key) { if (reduced && key === 'hub-motion') return 'off'; return store.has(key) ? store.get(key) : null; }, setItem(key, value) { store.set(key, value); } },
    fetch: async () => ({ ok: true, json: async () => ({ tools }) }),
    setTimeout(fn) { const id = ++timerId; timers.set(id, fn); return id; },
    clearTimeout(id) { timers.delete(id); },
    window: { addEventListener() {}, HubTools: Object.fromEntries(tools.map(({ id }) => [id, { mount(root) { mounted.push(id); root.innerHTML = id; return () => cleaned.push(id); } }])) },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8'), context);
  return {
    context, document, elements, mounted, cleaned, shell, store,
    run(code) { return vm.runInContext(code, context); },
    route(id) { context.location.hash = '#/' + id; vm.runInContext('route()', context); },
    flush() { for (const [id, fn] of [...timers]) { if (timers.delete(id)) fn(); } },
    key(key, shiftKey = false) { let prevented = false; listeners.get('keydown')?.({ key, shiftKey, preventDefault() { prevented = true; } }); return prevented; },
    dialog() { return document.body.children[0]; },
    opener() { const el = new Element(); el.focus(); return el; },
  };
}

async function ready(reduced = false) {
  const app = boot(reduced);
  await new Promise(resolve => setImmediate(resolve));
  return app;
}

test('navigation keeps old content during exit and mounts only latest requested tab', async () => {
  const app = await ready();
  app.route('b');
  assert.equal(app.elements.toolRoot.innerHTML, 'a');
  app.route('c');
  app.flush();
  assert.deepEqual(app.mounted, ['a', 'c']);
  assert.deepEqual(app.cleaned, ['a']);
});

test('returning to current tab cancels a pending exit without remounting', async () => {
  const app = await ready();
  app.route('b');
  app.route('a');
  app.flush();
  assert.deepEqual(app.mounted, ['a']);
  assert.deepEqual(app.cleaned, []);
  assert.equal(app.elements.toolRoot.classList.contains('is-exiting'), false);
});

test('motion off navigation does not wait for a timer', async () => {
  const app = await ready(true);
  app.route('b');
  assert.deepEqual(app.mounted, ['a', 'b']);
});

test('choice dialog focuses safe action, traps focus, and resolves choice once after close', async () => {
  const app = await ready();
  const opener = app.opener();
  const result = app.run('Hub.choose({title:"Delete?",text:"File",choices:[{value:"delete",label:"Delete",danger:true},{value:"trash",label:"Trash"}]})');
  const overlay = app.dialog();
  const buttons = overlay.querySelectorAll('button');
  const safe = buttons.find(button => button.dataset.choice === '1');
  assert.equal(app.document.activeElement, safe);
  assert.match(overlay.innerHTML, /aria-labelledby="hub-dialog-title-/);
  buttons.at(-1).focus();
  assert.equal(app.key('Tab'), true);
  assert.equal(app.document.activeElement, buttons[0]);
  assert.equal(app.key('Tab', true), true);
  assert.equal(app.document.activeElement, buttons.at(-1));
  overlay.click(safe);
  overlay.click(buttons.find(button => button.dataset.choice === '0'));
  assert.equal(overlay.isConnected, true);
  app.flush();
  assert.equal(await result, 'trash');
  assert.equal(overlay.isConnected, false);
  assert.equal(app.document.activeElement, opener);
  assert.equal(app.shell.inert, false);
});

test('danger-only confirm defaults to cancel and Escape preserves boolean API', async () => {
  const app = await ready();
  const result = app.run('Hub.confirm({title:"Delete?",text:"File",danger:true})');
  assert.equal(app.document.activeElement.dataset.act, 'cancel');
  app.key('Escape');
  app.flush();
  assert.equal(await result, false);
});

test('navigation overrides a choice still closing, preventing delayed mutation', async () => {
  const app = await ready();
  const result = app.run('Hub.choose({title:"Delete?",text:"File",choices:[{value:"delete",label:"Delete",danger:true}]})');
  app.dialog().click(app.dialog().children.find(button => button.dataset.choice === '0'));
  app.route('b');
  app.flush();
  assert.equal(await result, null);
  assert.equal(app.dialog(), undefined);
});

test('motion-off choice settles without waiting and confirm accepts once', async () => {
  const app = await ready(true);
  const result = app.run('Hub.confirm({title:"Continue?",text:"",confirmText:"Yes"})');
  const overlay = app.dialog();
  overlay.click(overlay.children.find(button => button.dataset.choice === '0'));
  assert.equal(app.dialog(), undefined);
  assert.equal(await result, true);
});

test('dialog escapes untrusted labels and text instead of creating injected markup', async () => {
  const app = await ready();
  const result = app.run('Hub.choose({title:"<img>",text:"<script>",choices:[{value:"safe",label:"<iframe>"}]})');
  assert.match(app.dialog().innerHTML, /&lt;img&gt;/);
  assert.match(app.dialog().innerHTML, /&lt;script&gt;/);
  assert.match(app.dialog().innerHTML, /&lt;iframe&gt;/);
  app.run('Hub.dismissDialog()');
  assert.equal(await result, null);
});

test('backdrop, replacement and explicit dismiss settle cancellation and clean listeners', async () => {
  const app = await ready();
  const first = app.run('Hub.choose({title:"One",text:"",choices:[]})');
  const second = app.run('Hub.choose({title:"Two",text:"",choices:[]})');
  assert.equal(await first, null);
  app.dialog().click();
  app.flush();
  assert.equal(await second, null);
  const third = app.run('Hub.choose({title:"Three",text:"",choices:[]})');
  app.run('Hub.dismissDialog()');
  assert.equal(await third, null);
  assert.equal(app.key('Escape'), false);
  assert.equal(app.dialog(), undefined);
});

test('motion is on by default and the toggle remembers the choice', async () => {
  const app = await ready();
  assert.equal(app.document.documentElement.dataset.motion, 'on');
  app.elements.motionBtn.click();
  assert.equal(app.document.documentElement.dataset.motion, 'off');
  assert.equal(app.elements.motionLabel.textContent, 'Анимации выключены');
  assert.equal(app.store.get('hub-motion'), 'off');
  app.elements.motionBtn.click();
  assert.equal(app.document.documentElement.dataset.motion, 'on');
  assert.equal(app.elements.motionLabel.textContent, 'Анимации включены');
  assert.equal(app.store.get('hub-motion'), 'on');
});

test('turning motion off makes tab switching immediate', async () => {
  const app = await ready();
  app.elements.motionBtn.click();
  app.route('b');
  assert.deepEqual(app.mounted, ['a', 'b']);
});
