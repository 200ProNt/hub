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
    version: '1.3.1.1',
    escapeHtml: (s) => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
    toast(m) { calls.push({ type: 'toast', message: m }); },
    playSound(type) { calls.push({ type: 'sound', sound: type }); },
    async api(url, body) {
      calls.push({ type: 'api', url, body });
      if (url === '/api/home/summary') {
        return {
          vitals: { cpu_percent: 15.2, memory_percent: 42.1, memory_used_gb: 6.7, memory_total_gb: 16.0 },
          todos: [{ note_id: 'note_1', note_title: 'Планы', line_idx: 0, text: 'Купить хлеб' }],
          recent_clips: [{ id: 'clip_1', preview: 'https://example.com' }],
          stats: { notes_count: 5, clipboard_count: 10, trash_count: 1, trash_size: 1024 },
          version: '1.3.1.1',
        };
      }
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

  const code = fs.readFileSync(path.join(__dirname, '../web/tools/home.js'), 'utf8');
  vm.runInNewContext(code, context);

  return { context, root: node('root'), calls };
}

test('home tool mounts and registers in HubTools', async () => {
  const { context, root, calls } = setup();
  assert.ok(context.window.HubTools.home, 'home tool must be registered');
  assert.equal(typeof context.window.HubTools.home.mount, 'function');

  const cleanup = context.window.HubTools.home.mount(root);
  assert.ok(root.innerHTML.includes('home-hero'));
  assert.ok(root.innerHTML.includes('home-grid'));

  // Allow loadSummary promise to resolve
  await new Promise((r) => setTimeout(r, 10));

  const apiCall = calls.find((c) => c.type === 'api' && c.url === '/api/home/summary');
  assert.ok(apiCall, 'should fetch /api/home/summary');

  if (typeof cleanup === 'function') cleanup();
});
