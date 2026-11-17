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
