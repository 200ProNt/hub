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
    defaultFolder: 'C:\\test',
    escapeHtml: (s) => String(s),
    fmtSize: (s) => `${s} Б`,
    toast(m) { calls.push({ type: 'toast', message: m }); },
    playSound(s) { calls.push({ type: 'sound', sound: s }); },
    async api(url, body) {
      calls.push({ type: 'api', url, body });
      if (url === '/api/info') return { default_folder: 'C:\\test' };
      if (url === '/api/renamer/scan') {
        return {
          folder: 'C:\\test',
          count: 2,
          files: [
            { name: 'photo_01.jpg', path: 'C:\\test\\photo_01.jpg', size: 100, mtime: 1000 },
            { name: 'photo_02.jpg', path: 'C:\\test\\photo_02.jpg', size: 200, mtime: 1000 },
          ],
        };
      }
      if (url === '/api/renamer/preview') {
        return {
          total: 2,
          ready_count: 2,
          unchanged_count: 0,
          conflict_count: 0,
          preview: [
            { old_name: 'photo_01.jpg', new_name: 'img_01.jpg', status: 'ok' },
            { old_name: 'photo_02.jpg', new_name: 'img_02.jpg', status: 'ok' },
          ],
        };
      }
      if (url === '/api/renamer/apply') {
        return { run_id: 'ren_123', renamed_count: 2, errors: [] };
      }
      return {};
    },
  };

  const code = fs.readFileSync(path.join(__dirname, '..', 'web', 'tools', 'renamer.js'), 'utf8');
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

test('renamer mounts and registers in HubTools', async () => {
  const { context, root } = setup();
  assert.ok(context.window.HubTools.renamer, 'HubTools.renamer should exist');
  assert.equal(typeof context.window.HubTools.renamer.mount, 'function');
  const cleanup = await context.window.HubTools.renamer.mount(root);
  assert.ok(root.innerHTML.includes('renamer-layout'), 'HTML should render layout');
  if (typeof cleanup === 'function') cleanup();
});
