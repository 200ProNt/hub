const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

/* Небольшая имитация DOM: элементам важны только текст, классы и data-атрибуты. */

function createDom() {
  const timers = [];
  const listeners = new Map();
  const store = new Map();

  class El {
    constructor(tag = 'div') {
      this.tagName = tag;
      this.dataset = {};
      this.attrs = {};
      this.handlers = {};
      this.children = [];
      this.parent = null;
      this.isConnected = true;
      this.disabled = false;
      this.inert = false;
      this.textContent = '';
      this._nodes = [];
      this._html = '';
      this._className = '';
      const classes = new Set();
      this.classList = {
        add: (...names) => names.forEach(name => classes.add(name)),
        remove: (...names) => names.forEach(name => classes.delete(name)),
        contains: name => classes.has(name),
        toggle: (name, force) => {
          const on = force === undefined ? !classes.has(name) : Boolean(force);
          if (on) classes.add(name);
          else classes.delete(name);
          return on;
        },
        values: () => [...classes],
      };
    }

    get className() { return this._className; }

    set className(value) {
      this._className = value;
      value.split(/\s+/).filter(Boolean).forEach(name => this.classList.add(name));
    }

    set innerHTML(html) {
      this._html = html;
      this._nodes = parseNodes(html);
      this.children = this._nodes;
    }

    get innerHTML() { return this._html; }

    setAttribute(name, value) { this.attrs[name] = value; }
    addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); }
    appendChild(child) { this.children.push(child); child.parent = this; return child; }
    querySelector(selector) { return this._nodes.find(node => matches(node, selector)) || null; }
    querySelectorAll(selector) { return this._nodes.filter(node => matches(node, selector)); }
    contains(node) { return node === this || this._nodes.includes(node); }
    closest(selector) { return matches(this, selector) ? this : null; }
    focus() { document.activeElement = this; }
    remove() {
      this.isConnected = false;
      if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
    }

    click(target = this) {
      (this.handlers.click || []).forEach(fn => fn({ target }));
    }
  }

  function dataKey(name) {
    return name.slice(5).replace(/-(\w)/g, (_, letter) => letter.toUpperCase());
  }

  function parseNodes(html) {
    const nodes = [];
    const re = /<([a-zA-Z][\w-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g;
    let match;
    while ((match = re.exec(html))) {
      const el = new El(match[1].toLowerCase());
      for (const [, name, value] of match[2].matchAll(/([\w-]+)="([^"]*)"/g)) {
        if (name === 'id') el.attrs.id = value;
        else if (name === 'class') el.className = value;
        else if (name.startsWith('data-')) el.dataset[dataKey(name)] = value;
        else el.attrs[name] = value;
      }
      const rest = html.slice(re.lastIndex);
      const end = rest.indexOf('<');
      el.textContent = (end === -1 ? rest : rest.slice(0, end)).trim();
      nodes.push(el);
    }
    return nodes;
  }

  function matches(el, selector) {
    const id = /^#(.+)$/.exec(selector);
    if (id) return el.attrs.id === id[1];
    const data = /^\[data-([\w-]+)(?:="([^"]+)")?\]$/.exec(selector);
    if (data) {
      const key = dataKey(`data-${data[1]}`);
      return data[2] === undefined ? key in el.dataset : el.dataset[key] === data[2];
    }
    const cssClass = /^\.([\w-]+)$/.exec(selector);
    if (cssClass) return el.classList.contains(cssClass[1]);
    return el.tagName === selector;
  }

  const elements = {
    splash: new El('div'),
    shell: new El('div'),
  };
  elements.splash.className = 'splash';

  const document = {
    activeElement: null,
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    removeEventListener(type, fn) {
      listeners.set(type, (listeners.get(type) || []).filter(item => item !== fn));
    },
    createElement: tag => new El(tag),
    getElementById: id => elements[id] || null,
    querySelector: selector => (selector === '.shell' ? elements.shell : null),
  };

  document.documentElement = new El('html');
  document.body = new El('body');
  document.body.appendChild(elements.shell);

  const context = vm.createContext({
    document,
    Date,
    window: {
      setTimeout(fn) { timers.push(fn); return timers.length; },
      clearTimeout() {},
    },
    localStorage: {
      getItem: key => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => store.set(key, value),
    },
  });

  function flush() {
    let guard = 0;
    while (timers.length && guard < 200) {
      guard += 1;
      timers.shift()();
    }
  }

  function key(name, shiftKey = false) {
    let prevented = false;
    for (const fn of [...(listeners.get('keydown') || [])]) {
      fn({ key: name, shiftKey, preventDefault() { prevented = true; } });
    }
    return prevented;
  }

  return {
    context, document, elements, store,
    run(code) { return vm.runInContext(code, context); },
    load() { vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/intro.js'), 'utf8'), context); },
    flush,
    key,
    intro() { return document.body.children.find(child => child.classList.contains('intro')) || null; },
  };
}

function boot({ onboarded = false, motion = 'on' } = {}) {
  const dom = createDom();
  dom.document.documentElement.dataset.motion = motion;
  if (onboarded) dom.store.set('hub-onboarded', '1');
  dom.load();
  return dom;
}

function press(dom, selector) {
  const button = dom.intro().querySelector(selector);
  dom.intro().click(button);
  return button;
}

const next = dom => dom.intro().querySelector('[data-act="next"]');
const back = dom => dom.intro().querySelector('[data-act="back"]');
const title = dom => dom.intro().querySelector('[data-intro="title"]');
const text = dom => dom.intro().querySelector('[data-intro="text"]');
const step = dom => dom.intro().querySelector('[data-intro="step"]');
const dots = dom => dom.intro().querySelector('[data-intro="dots"]');

test('the page ships a splash screen and loads the intro before the app', () => {
  const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
  assert.match(html, /id="splash"/);
  assert.match(html, /class="splash-mark"/);
  assert.ok(html.indexOf('src="intro.js"') < html.indexOf('src="app.js"'));
});

test('the splash screen waits for the app and then leaves', () => {
  const dom = boot();
  dom.run('window.HubIntro.ready()');
  dom.flush();
  assert.equal(dom.elements.splash.isConnected, false);
});

test('a first launch explains the hub instead of dumping the user into it', () => {
  const dom = boot();
  dom.run('window.HubIntro.ready()');
  dom.flush();

  const intro = dom.intro();
  assert.ok(intro);
  assert.match(intro.innerHTML, /role="dialog"/);
  assert.match(intro.innerHTML, /aria-modal="true"/);
  assert.equal(title(dom).textContent, 'Привет, это Hub');
  assert.equal(step(dom).textContent, 'Знакомство');
  assert.equal(next(dom).textContent, 'Показать, как пользоваться');
  assert.equal(back(dom).classList.contains('hidden'), true);
  assert.equal(dots(dom).classList.contains('intro-chips'), true);
  assert.equal(dots(dom).querySelectorAll('span').length, 3);
  assert.equal(dom.elements.shell.inert, true);
  assert.equal(dom.document.activeElement, next(dom));
});

test('steps move forward and back with a counter and dots', () => {
  const dom = boot();
  dom.run('window.HubIntro.ready()');
  dom.flush();

  press(dom, '[data-act="next"]');
  assert.equal(step(dom).textContent, 'Шаг 1 из 4');
  assert.equal(back(dom).classList.contains('hidden'), false);
  assert.equal(dots(dom).classList.contains('intro-chips'), false);
  assert.equal(dots(dom).querySelectorAll('i').length, 4);
  assert.equal(dots(dom).querySelectorAll('i')[0].classList.contains('is-active'), true);

  press(dom, '[data-act="next"]');
  assert.equal(step(dom).textContent, 'Шаг 2 из 4');
  assert.equal(dots(dom).querySelectorAll('i')[1].classList.contains('is-active'), true);
  assert.equal(dots(dom).querySelectorAll('i')[0].classList.contains('is-active'), false);

  press(dom, '[data-act="back"]');
  assert.equal(step(dom).textContent, 'Шаг 1 из 4');

  dom.key('ArrowRight');
  dom.key('ArrowRight');
  dom.key('ArrowRight');
  assert.equal(next(dom).textContent, 'Начать');
  assert.ok(text(dom).textContent.includes('data/'));
});

test('skipping closes the tour and remembers the choice', () => {
  const dom = boot();
  dom.run('window.HubIntro.ready()');
  dom.flush();

  press(dom, '[data-act="skip"]');
  assert.equal(dom.store.get('hub-onboarded'), '1');
  dom.flush();
  assert.equal(dom.intro(), null);
  assert.equal(dom.elements.shell.inert, false);
});

test('finishing the last step also remembers the choice', () => {
  const dom = boot();
  dom.run('window.HubIntro.ready()');
  dom.flush();

  for (let index = 0; index < 4; index += 1) press(dom, '[data-act="next"]');
  assert.equal(next(dom).textContent, 'Начать');
  press(dom, '[data-act="next"]');
  dom.flush();
  assert.equal(dom.intro(), null);
  assert.equal(dom.store.get('hub-onboarded'), '1');
});

test('Escape leaves the tour as if skipped', () => {
  const dom = boot();
  dom.run('window.HubIntro.ready()');
  dom.flush();

  assert.equal(dom.key('Escape'), true);
  dom.flush();
  assert.equal(dom.intro(), null);
  assert.equal(dom.store.get('hub-onboarded'), '1');
});

test('later launches go straight to the tools', () => {
  const dom = boot({ onboarded: true });
  dom.run('window.HubIntro.ready()');
  dom.flush();
  assert.equal(dom.intro(), null);
  assert.equal(dom.elements.splash.isConnected, false);
});

test('with motion off the splash is skipped and the tour opens at once', () => {
  const dom = boot({ motion: 'off' });
  dom.run('window.HubIntro.ready()');
  dom.flush();
  assert.equal(dom.elements.splash.isConnected, false);
  assert.ok(dom.intro());
});

test('the tour can be replayed from the about page even after it was skipped', () => {
  const dom = boot({ onboarded: true });
  dom.run('window.HubIntro.ready()');
  dom.flush();
  assert.equal(dom.intro(), null);

  dom.run('window.HubIntro.open()');
  assert.ok(dom.intro());
  assert.equal(title(dom).textContent, 'Привет, это Hub');

  dom.run('window.HubIntro.open()');
  assert.equal(dom.document.body.children.filter(child => child.classList.contains('intro')).length, 1);

  press(dom, '[data-act="skip"]');
  dom.flush();
  assert.equal(dom.intro(), null);
});

test('the about page offers to replay the tour', () => {
  const source = fs.readFileSync(path.join(__dirname, '../web/tools/about.js'), 'utf8');
  assert.match(source, /id="aboutIntro"/);
  assert.match(source, /HubIntro\.open\(\)/);
});
