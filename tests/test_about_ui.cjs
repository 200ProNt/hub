const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const ABOUT = {
  name: 'Hub',
  version: '1.0.0',
  author: 'devrin',
  license: 'MIT',
  license_text: 'MIT License\n\nCopyright (c) 2026 devrin\n<script>alert(1)</script>',
  folder: 'C:\\hub',
  readme: 'C:\\hub\\README.md',
  tools: 10,
  python: '3.14.10',
  changes: [
    {
      version: '1.1.1',
      date: '2026-11-17',
      items: ['История версий на странице «О программе».'],
    },
    {
      version: '1.1.0',
      date: '2026-10-02',
      items: ['Корзина стала вкладкой.', 'Поиск по Ctrl+K.', '<b>не разметка</b>'],
    },
    { version: '1.0.0', date: '2026-09-01', items: ['Первая версия.'] },
  ],
};

function setup() {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) {
      nodes.set(key, {
        innerHTML: '',
        textContent: '',
        title: '',
        listeners: {},
        addEventListener(type, fn) { this.listeners[type] = fn; },
        querySelector(selector) { return node(`${key} ${selector}`); },
      });
    }
    return nodes.get(key);
  };

  const calls = [];
  const Hub = {
    version: '9.9.9',
    tools: new Array(9).fill({ id: 'x' }),
    toast() {},
    escapeHtml(value) {
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    },
    async api(url, body) {
      calls.push({ url, body });
      if (url === '/api/about') return ABOUT;
      return { ok: true };
    },
  };

  const context = { window: { HubTools: {} }, Hub, console };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/tools/about.js'), 'utf8'), context);
  const root = { innerHTML: '', querySelector: node };
  const cleanup = context.window.HubTools.about.mount(root);
  return { node, calls, cleanup, root };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

test('about page shows version, author, tools and license', async () => {
  const s = setup();
  await settle();
  assert.ok(s.root.innerHTML.includes('devrin'));
  assert.ok(s.root.innerHTML.includes('История версий'));
  assert.equal(s.node('#aboutVersion').textContent, 'версия 1.0.0');
  assert.equal(s.node('#aboutVersionValue').textContent, '1.0.0');
  assert.equal(s.node('#aboutTools').textContent, '10');
  assert.equal(s.node('#aboutFolder').textContent, 'C:\\hub');
  assert.equal(s.node('#aboutFolder').title, 'C:\\hub');
  assert.ok(s.calls.some((call) => call.url === '/api/about'));
});

test('license text is inserted as text, not markup', async () => {
  const s = setup();
  await settle();
  const license = s.node('#aboutLicenseText');
  assert.ok(license.textContent.includes('MIT License'));
  assert.ok(license.textContent.includes('<script>'));
  assert.equal(license.innerHTML, '');
});

test('buttons open the project folder and the README', async () => {
  const s = setup();
  await settle();
  await s.node('#aboutOpen').listeners.click();
  await s.node('#aboutReadme').listeners.click();
  const calls = s.calls.filter((call) => call.url === '/api/open');
  assert.equal(calls.length, 2);
  assert.equal(calls[0].body.path, 'C:\\hub');
  assert.equal(calls[1].body.path, 'C:\\hub\\README.md');
});

test('an unmounted page cannot open folders', async () => {
  const s = setup();
  await settle();
  s.cleanup();
  await s.node('#aboutOpen').listeners.click();
  assert.ok(!s.calls.some((call) => call.url === '/api/open'));
});

test('release history is rendered newest first with the current badge', async () => {
  const s = setup();
  await settle();
  const markup = s.node('#aboutReleases').innerHTML;
  assert.ok(markup.includes('1.1.1'));
  assert.ok(markup.includes('1.1.0'));
  assert.ok(markup.includes('1.0.0'));
  assert.ok(markup.indexOf('1.1.1') < markup.indexOf('1.1.0'));
  assert.ok(markup.includes('<span class="about-release-badge">сейчас</span>'));
  assert.ok(markup.includes('17 ноября 2026'));
  assert.ok(markup.includes('2 октября 2026'));
  assert.ok(markup.includes('is-latest'));
});

test('release items are escaped and the markup is not executed', async () => {
  const s = setup();
  await settle();
  const markup = s.node('#aboutReleases').innerHTML;
  assert.ok(!markup.includes('<b>не разметка</b>'));
  assert.ok(markup.includes('&lt;b&gt;не разметка&lt;/b&gt;'));
});

test('history list keeps the empty state when changes are absent', async () => {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) {
      nodes.set(key, {
        innerHTML: '',
        textContent: '',
        title: '',
        listeners: {},
        addEventListener(type, fn) { this.listeners[type] = fn; },
        querySelector(selector) { return node(`${key} ${selector}`); },
      });
    }
    return nodes.get(key);
  };
  const Hub = {
    version: '1.1.1',
    tools: [],
    toast() {},
    escapeHtml(value) {
      return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
    },
    async api(url) {
      if (url === '/api/about') return { name: 'Hub', version: '1.1.1', tools: 0 };
      return { ok: true };
    },
  };
  const context = { window: { HubTools: {} }, Hub, console };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/tools/about.js'), 'utf8'), context);
  context.window.HubTools.about.mount({ innerHTML: '', querySelector: node });
  await settle();
  assert.equal(node('#aboutReleases').innerHTML, '<li class="about-release-empty">История пока пустая.</li>');
});

test('initial render shows loading state while waiting for api', () => {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) {
      nodes.set(key, {
        innerHTML: '',
        textContent: '',
        title: '',
        listeners: {},
        addEventListener(type, fn) { this.listeners[type] = fn; },
        querySelector(selector) { return node(`${key} ${selector}`); },
      });
    }
    return nodes.get(key);
  };
  const Hub = {
    version: '1.1.1',
    tools: [],
    toast() {},
    escapeHtml(value) { return String(value); },
    api() { return new Promise(() => {}); },
  };
  const context = { window: { HubTools: {} }, Hub, console };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/tools/about.js'), 'utf8'), context);
  context.window.HubTools.about.mount({ innerHTML: '', querySelector: node });
  assert.equal(node('#aboutReleases').innerHTML, '<li class="about-release-empty">Загружаю…</li>');
  assert.equal(node('#aboutLicenseText').textContent, 'Загружаю…');
});
