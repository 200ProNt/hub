const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const MB = 1024 * 1024;
const GB = 1024 * MB;

const SNAPSHOT = {
  ready: true,
  time: 0,
  seconds: 1.2,
  system: {
    cpu: 12.5,
    cores: 8,
    memory: { total: 16 * GB, used: 8 * GB, percent: 50 },
    disk: { total: 500 * GB, free: 120 * GB, percent: 76 },
    uptime: 90_000,
    processes: 3,
  },
  processes: [
    { pid: 100, name: 'chrome.exe', cpu: 20.5, memory: 500 * MB, started: 1_763_000_000, created: 1, session: 1, can_stop: true, why_not: '', own: false },
    { pid: 200, name: 'game.exe', cpu: 5, memory: 900 * MB, started: 1_763_000_000, created: 1, session: 1, can_stop: true, why_not: '', own: false },
    { pid: 4, name: 'System', cpu: 0, memory: 0, started: 0, created: 1, session: 0, can_stop: false, why_not: 'Это системный процесс Windows', own: false },
  ],
};

function setup(confirmResult = true) {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) {
      const classes = new Set();
      nodes.set(key, {
        innerHTML: '',
        textContent: '',
        value: '',
        dataset: {},
        disabled: false,
        style: {},
        attrs: {},
        getAttribute(name) { return this.attrs[name] ?? null; },
        setAttribute(name, value) { this.attrs[name] = String(value); },
        listeners: {},
        classList: {
          add(name) { classes.add(name); },
          remove(name) { classes.delete(name); },
          toggle(name, force) {
            if (force === undefined ? !classes.has(name) : force) classes.add(name);
            else classes.delete(name);
          },
          contains(name) { return classes.has(name); },
        },
        addEventListener(type, fn) { this.listeners[type] = fn; },
        querySelectorAll() { return []; },
        querySelector(selector) { return node(`${key} ${selector}`); },
        focus() {},
      });
    }
    return nodes.get(key);
  };

  const calls = [];
  const Hub = {
    escapeHtml: String,
    plural: (count, one, few, many) => (count === 1 ? one : count < 5 ? few : many),
    fmtSize: (bytes) => `${bytes} Б`,
    toast() {},
    setBusy() {},
    dismissDialog() {},
    async confirm() { return confirmResult; },
    async api(url, body) {
      calls.push({ url, body });
      if (url.endsWith('/terminate')) return { stopped: true, pid: body.pid, name: 'chrome.exe' };
      return SNAPSHOT;
    },
  };

  const document = {
    hidden: false,
    listeners: {},
    addEventListener(type, fn) { this.listeners[type] = fn; },
    removeEventListener(type) { delete this.listeners[type]; },
  };

  const context = {
    window: { HubTools: {} },
    Hub,
    document,
    console,
    setTimeout: () => 1,
    clearTimeout: () => {},
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/tools/monitor.js'), 'utf8'), context);
  const root = { innerHTML: '', querySelector: node };
  const cleanup = context.window.HubTools.monitor.mount(root);
  return { node, calls, cleanup, document };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

function clickClose(pid = '100', name = 'chrome.exe') {
  const button = {
    dataset: { pid, name },
    classList: { contains: (value) => value === 'mon-close' },
    closest: () => button,
  };
  return { target: { closest: () => button } };
}

test('snapshot fills the vitals and the process list', async () => {
  const s = setup();
  await settle();
  assert.equal(s.node('#monCpu').textContent, '12,5%');
  assert.ok(s.node('#monCpuSub').textContent.includes('8 ядер'));
  assert.equal(s.node('#monRam').textContent, '50%');
  assert.equal(s.node('#monDisk').textContent, '24%');
  assert.equal(s.node('#monUptime').textContent, '1 день 1 ч');
  assert.equal(s.node('#monCount').textContent, '3');
  assert.ok(s.node('#monList').innerHTML.includes('chrome.exe'));
  assert.equal(s.calls.filter((call) => call.url === '/api/monitor/snapshot').length, 1);
  s.cleanup();
});

test('system processes show a lock instead of a close button', async () => {
  const s = setup();
  await settle();
  const html = s.node('#monList').innerHTML;
  assert.ok(html.includes('mon-lock'));
  assert.ok(!html.includes('data-pid="4" data-name'));
  assert.equal((html.match(/mon-close/g) || []).length, 2);
  assert.ok(html.includes('data-pid="100" data-name="chrome.exe"'));
  s.cleanup();
});

test('closing a process asks for confirmation first', async () => {
  const s = setup(true);
  await settle();
  await s.node('#monList').listeners.click(clickClose());
  await settle();
  await settle();
  const request = s.calls.find((call) => call.url === '/api/monitor/terminate');
  assert.equal(request.body.pid, 100);
  assert.ok(s.calls.filter((call) => call.url === '/api/monitor/snapshot').length >= 2);
  s.cleanup();
});

test('declining confirmation leaves the process alone', async () => {
  const s = setup(false);
  await settle();
  await s.node('#monList').listeners.click(clickClose());
  await settle();
  assert.ok(!s.calls.some((call) => call.url === '/api/monitor/terminate'));
  s.cleanup();
});

test('pause and resume update the live indicator', async () => {
  const s = setup();
  await settle();
  s.node('#monPause').listeners.click();
  assert.equal(s.node('#monLiveText').textContent, 'на паузе');
  assert.equal(s.node('#monPause').textContent, 'Продолжить');
  assert.equal(s.node('#monPause').getAttribute('aria-pressed'), 'true');
  s.node('#monPause').listeners.click();
  await settle();
  assert.equal(s.node('#monLiveText').textContent, 'обновляется каждые 2 с');
  assert.equal(s.node('#monPause').textContent, 'Пауза');
  s.cleanup();
});

test('search filters by name and pid', async () => {
  const s = setup();
  await settle();
  s.node('#monQuery').listeners.input({ target: { value: 'game' } });
  assert.ok(s.node('#monList').innerHTML.includes('game.exe'));
  assert.ok(!s.node('#monList').innerHTML.includes('chrome.exe'));
  assert.equal(s.node('#monCount').textContent, '1 из 3');

  s.node('#monQuery').listeners.input({ target: { value: '200' } });
  assert.ok(s.node('#monList').innerHTML.includes('game.exe'));
  assert.ok(!s.node('#monList').innerHTML.includes('chrome.exe'));

  s.node('#monQuery').listeners.input({ target: { value: 'ничего' } });
  assert.ok(s.node('#monList').innerHTML.includes('Ничего не нашлось'));
  s.cleanup();
});

test('sorting by memory puts the heaviest process first', async () => {
  const s = setup();
  await settle();
  s.node('#monSort').listeners.change({ target: { value: 'memory' } });
  const html = s.node('#monList').innerHTML;
  assert.ok(html.indexOf('game.exe') < html.indexOf('chrome.exe'));
  s.node('#monSort').listeners.change({ target: { value: 'name' } });
  const byName = s.node('#monList').innerHTML;
  assert.ok(byName.indexOf('chrome.exe') < byName.indexOf('game.exe'));
  s.cleanup();
});

test('an unmounted tool cannot close processes', async () => {
  const s = setup();
  await settle();
  s.cleanup();
  s.node('#monList').listeners.click(clickClose());
  await settle();
  assert.ok(!s.calls.some((call) => call.url === '/api/monitor/terminate'));
});
