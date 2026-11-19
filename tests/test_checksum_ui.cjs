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
        checked: true,
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
      if (url === '/api/checksum/password') {
        return { password: 'secret_password_123', entropy: 70, strength: 'strong' };
      }
      return {};
    },
  };

  const code = fs.readFileSync(path.join(__dirname, '..', 'web', 'tools', 'checksum.js'), 'utf8');
  const context = {
    window: {},
    Hub,
    clearTimeout,
    setTimeout,
    document: {
      addEventListener() {},
    },
  };
  context.window.HubTools = {};
  vm.createContext(context);
  vm.runInContext(code, context);

  return { context, Hub, calls, root: node('root') };
}

test('checksum mounts and registers in HubTools', async () => {
  const { context, root } = setup();
  assert.ok(context.window.HubTools.checksum, 'HubTools.checksum should exist');
  assert.equal(typeof context.window.HubTools.checksum.mount, 'function');
  const cleanup = await context.window.HubTools.checksum.mount(root);
  assert.ok(root.innerHTML.includes('crypto-layout'), 'HTML should render crypto-layout');
  if (typeof cleanup === 'function') cleanup();
});
