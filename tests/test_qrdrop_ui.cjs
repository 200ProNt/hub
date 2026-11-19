const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

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
        style: {},
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
      });
    }
    return nodes.get(key);
  };

  const calls = [];
  const Hub = {
    escapeHtml: (s) => String(s),
    fmtSize: (s) => `${s} Б`,
    timeAgo: () => 'только что',
    toast(m) { calls.push({ type: 'toast', message: m }); },
    playSound(s) { calls.push({ type: 'sound', sound: s }); },
    async api(url, body) {
      calls.push({ type: 'api', url, body });
      if (url === '/api/drop/info') {
        return {
          ip: '192.168.1.50',
          port: 8770,
          url: 'http://192.168.1.50:8770/drop',
          shared_files: [{ name: 'file1.txt', size: 1024, mtime: 1000, url: '/api/drop/download?name=file1.txt' }],
          incoming_files: [],
          incoming_texts: [{ text: 'Привет!', date: '2026-11-19 12:00' }],
        };
      }
      return {};
    },
  };

  const code = fs.readFileSync(path.join(__dirname, '..', 'web', 'tools', 'qrdrop.js'), 'utf8');
  const context = {
    window: {},
    Hub,
    clearTimeout,
    setTimeout,
    setInterval,
    clearInterval,
    TextEncoder,
    document: {
      addEventListener() {},
    },
  };
  context.window.HubTools = {};
  vm.createContext(context);
  vm.runInContext(code, context);

  return { context, Hub, calls, root: node('root') };
}

test('qrdrop mounts and registers in HubTools', async () => {
  const { context, root } = setup();
  assert.ok(context.window.HubTools.qrdrop, 'HubTools.qrdrop should exist');
  assert.equal(typeof context.window.HubTools.qrdrop.mount, 'function');
  const cleanup = await context.window.HubTools.qrdrop.mount(root);
  assert.ok(root.innerHTML.includes('qrdrop-layout'), 'HTML should render qrdrop-layout');
  if (typeof cleanup === 'function') cleanup();
});

test('qrdrop cleanup returns sync function and stops unmounted toasts', () => {
  const { context, root, calls } = setup();
  root.isConnected = true;
  const cleanup = context.window.HubTools.qrdrop.mount(root);
  assert.equal(typeof cleanup, 'function', 'mount must return a synchronous cleanup function');
  
  root.isConnected = false;
  cleanup();
  root.innerHTML = '';

  const toastsAfterUnmount = calls.filter(c => c.type === 'toast');
  assert.equal(toastsAfterUnmount.length, 0, 'no toast error should be fired after unmount');
});
