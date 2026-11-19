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
        value: '80',
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
    defaultFolder: 'C:\\demo',
    escapeHtml: String,
    plural: () => 'файлов',
    fmtSize: (s) => `${s} Б`,
    toast(m) { calls.push({ type: 'toast', message: m }); },
    setBusy() {},
    dismissDialog() {},
    async api(url, body) {
      calls.push({ type: 'api', url, body });
      if (url === '/api/info') return { default_folder: 'C:\\demo' };
      if (url === '/api/images/save') return { ok: true, filename: 'test.webp' };
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
    URL: {
      createObjectURL: () => 'blob:mock',
      revokeObjectURL: () => {},
    },
    document: {
      createElement: () => ({ getContext: () => ({ drawImage() {} }), toBlob(cb) { cb(new Blob()); } }),
      body: { appendChild() {}, removeChild() {} },
    },
    FileReader: function () {
      this.readAsDataURL = function () {
        setTimeout(() => { if (this.onload) this.onload(); if (this.onloadend) this.onloadend(); }, 0);
      };
    },
    Image: function () {
      setTimeout(() => { this.width = 100; this.height = 100; if (this.onload) this.onload(); }, 0);
    },
    console,
  };

  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/tools/images.js'), 'utf8'), context);
  const root = { innerHTML: '', querySelector: node };
  const cleanup = context.window.HubTools.images.mount(root);
  return { node, calls, cleanup };
}

test('images tool mounts and registers in HubTools', () => {
  const { node, cleanup } = setup();
  assert.ok(node('#imgDropZone'));
  assert.ok(node('#imgFormatGroup'));
  assert.ok(node('#imgQualitySlider'));
  assert.ok(node('#imgGrid'));
  assert.equal(typeof cleanup, 'function');
  cleanup();
});

test('images tool sets format on slider input', () => {
  const { node, cleanup } = setup();
  const slider = node('#imgQualitySlider');
  slider.value = '60';
  if (slider.listeners['input']) {
    slider.listeners['input']({ target: slider });
  }
  assert.equal(node('#imgQualityVal').textContent, '60%');
  cleanup();
});
