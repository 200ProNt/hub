const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function boot() {
  const listeners = new Map();
  const elements = new Map();

  class Element {
    constructor(id = '') {
      this.id = id;
      this.dataset = {};
      this.classList = {
        classes: new Set(id === 'settingsModal' ? ['modal', 'hidden'] : []),
        add(c) { this.classes.add(c); },
        remove(c) { this.classes.delete(c); },
        toggle(c, v) { if (v) this.classes.add(c); else this.classes.delete(c); },
        contains(c) { return this.classes.has(c); },
      };
      this.handlers = {};
    }
    setAttribute(k, v) { this[k] = v; }
    getAttribute(k) { return this[k]; }
    removeAttribute(k) { delete this[k]; }
    addEventListener(t, fn) { this.handlers[t] = fn; }
    querySelector() { return new Element(); }
    querySelectorAll() { return []; }
    focus() {}
    click(e = {}) { this.handlers.click?.(e); }
  }

  const el = (id) => {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  };

  const document = {
    activeElement: null,
    documentElement: new Element(),
    getElementById: (id) => el(id),
    querySelector: () => new Element(),
    querySelectorAll: () => [],
    addEventListener(t, fn) { listeners.set(t, fn); },
  };

  const window = {
    addEventListener(t, fn) { listeners.set(t, fn); },
    HubTools: {},
  };

  const context = {
    document,
    window,
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    location: { hash: '#/home' },
    fetch: async () => ({ ok: true, json: async () => ({ tools: [{ id: 'home', name: 'Главная' }] }) }),
    setTimeout: () => 1,
    clearTimeout: () => {},
    console,
  };

  const code = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
  vm.runInNewContext(code, context);

  return { context, el, listeners, window };
}

test('settings modal opens and closes via Hub API', async () => {
  const { context, el, window } = boot();
  const modal = el('settingsModal');
  assert.equal(modal.classList.contains('hidden'), true);

  window.Hub.openSettings();
  assert.equal(modal.classList.contains('hidden'), false);

  window.Hub.closeSettings();
  assert.equal(modal.classList.contains('hidden'), true);
});

test('settings modal toggles on Ctrl+, keydown', async () => {
  const { context, el, listeners } = boot();
  const modal = el('settingsModal');
  assert.equal(modal.classList.contains('hidden'), true);

  const keydown = listeners.get('keydown');
  assert.ok(keydown, 'keydown listener should be attached');

  let prevented = false;
  keydown({ ctrlKey: true, key: ',', preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(modal.classList.contains('hidden'), false);

  keydown({ ctrlKey: true, key: ',', preventDefault() {} });
  assert.equal(modal.classList.contains('hidden'), true);
});
