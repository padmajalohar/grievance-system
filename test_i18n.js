const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class MockElement {
  constructor(tagName = 'div', attributes = {}) {
    this.tagName = tagName;
    this.attributes = { ...attributes };
    this.children = [];
    this.listeners = {};
    this.dataset = {};
    this.textContent = '';
    this.value = '';
    this.htmlFor = '';
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  getAttribute(name) {
    return this.attributes[name] || null;
  }

  appendChild(child) {
    this.children.push(child);
    if (this.tagName === 'select' && !this.value) this.value = child.value;
    return child;
  }

  append(...children) {
    children.forEach(child => this.appendChild(child));
  }

  addEventListener(name, handler) {
    (this.listeners[name] ||= []).push(handler);
  }

  dispatch(name) {
    (this.listeners[name] || []).forEach(handler => handler({ target: this }));
  }
}

class MockTextNode {
  constructor(value) {
    this.nodeValue = value;
    this.parentElement = { closest: () => null };
  }
}

class MockCustomEvent {
  constructor(type, options) {
    this.type = type;
    this.detail = options.detail;
  }
}

function createI18nContext(language = null, host = null) {
  const textNodes = [
    new MockTextNode('Make your voice '),
    new MockTextNode('count.')
  ];
  const input = new MockElement('input', { placeholder: 'Give your complaint a clear title' });
  const markedElement = new MockElement('span');
  markedElement.dataset.i18n = 'Civic Impact Rewards';
  const saved = new Map();
  const documentEvents = {};
  const body = new MockElement('body');
  body.querySelectorAll = () => [input];
  body.appendChild = function appendChild(child) {
    this.children.push(child);
    this.languageControl = child;
  };
  const document = {
    title: 'Sign in | ResolveAI',
    documentElement: { lang: 'en' },
    body,
    querySelector() {
      return host;
    },
    addEventListener(name, handler) {
      (documentEvents[name] ||= []).push(handler);
    },
    dispatchEvent() {},
    createElement(tagName) {
      return new MockElement(tagName);
    },
    createTreeWalker(_root, _filter) {
      let index = 0;
      return { nextNode: () => textNodes[index++] || null };
    },
    querySelectorAll(selector) {
      return selector === '[data-i18n]' ? [markedElement] : [];
    }
  };
  const localStorage = {
    getItem(key) {
      return saved.has(key) ? saved.get(key) : (key === 'resolve_language' ? language : null);
    },
    setItem(key, value) {
      saved.set(key, value);
    }
  };
  const window = {};
  const context = {
    window,
    document,
    localStorage,
    NodeFilter: { SHOW_TEXT: 4 },
    CustomEvent: MockCustomEvent
  };
  vm.runInNewContext(fs.readFileSync('js/i18n.js', 'utf8'), context, { filename: 'i18n.js' });

  return {
    context,
    document,
    input,
    localStorage,
    markedElement,
    host,
    textNodes,
    initialize: () => documentEvents.DOMContentLoaded[0]()
  };
}

const setup = createI18nContext();
const i18n = setup.context.window.ResolveAIi18n;
assert.deepEqual(Array.from(i18n.languages), ['en', 'mr', 'hi', 'kn', 'te']);
assert.equal(i18n.translate('missing translation key'), 'missing translation key');
assert.equal(i18n.translate('{{count}} of {{total}} complaints', { count: 2, total: 5 }), '2 of 5 complaints');

for (const language of i18n.languages) {
  for (const [english, translated] of Object.entries(i18n.dictionary[language])) {
    assert.ok(translated, `${language} has a non-empty translation for ${english}`);
  }
}

for (const language of ['mr', 'hi', 'kn', 'te']) {
  for (const key of ['Department Staff', 'Department dashboard', 'Assigned complaints', 'Create department account', 'Critical priority', 'High priority', 'Medium priority', 'Low priority']) {
    assert.notEqual(i18n.dictionary[language][key], key, `${language} translates ${key}`);
  }
}

setup.initialize();
const picker = setup.document.body.languageControl.children[1];
assert.equal(picker.value, 'en');
assert.equal(setup.document.documentElement.lang, 'en');
assert.equal(setup.document.title, 'Sign in | ResolveAI');

const header = new MockElement('header');
const headerSetup = createI18nContext(null, header);
headerSetup.initialize();
assert.equal(header.children[0].className, 'language-control');
assert.equal(headerSetup.document.body.languageControl, undefined);

const samples = {
  mr: ['mr-IN', 'तुमचा आवाज', 'साइन इन | ResolveAI'],
  hi: ['hi-IN', 'अपनी आवाज़', 'साइन इन | ResolveAI'],
  kn: ['kn-IN', 'ನಿಮ್ಮ ಧ್ವನಿಯನ್ನು', 'ಸೈನ್ ಇನ್ | ResolveAI'],
  te: ['te-IN', 'మీ స్వరాన్ని', 'సైన్ ఇన్ | ResolveAI']
};
for (const [language, [locale, translatedHeading, translatedTitle]] of Object.entries(samples)) {
  picker.value = language;
  picker.dispatch('change');
  assert.equal(setup.localStorage.getItem('resolve_language'), language);
  assert.equal(setup.document.documentElement.lang, locale);
  assert.equal(setup.textNodes.map(node => node.nodeValue).join(''), `${translatedHeading} ${i18n.translate('count.')}`);
  assert.equal(setup.input.getAttribute('placeholder'), i18n.translate('Give your complaint a clear title'));
  assert.equal(setup.document.title, translatedTitle);
  assert.equal(setup.markedElement.textContent, i18n.translate('Civic Impact Rewards'));
}

picker.value = 'en';
picker.dispatch('change');
assert.equal(setup.textNodes.map(node => node.nodeValue).join(''), 'Make your voice count.');
assert.equal(setup.input.getAttribute('placeholder'), 'Give your complaint a clear title');

const persisted = createI18nContext('kn');
persisted.initialize();
assert.equal(persisted.document.documentElement.lang, 'kn-IN');
assert.equal(persisted.document.body.languageControl.children[1].value, 'kn');

console.log('PASS: five-language dictionary, fallback, interpolation, browser-language persistence, selector changes, document lang/title, static text, dynamic marked text, and placeholders.');
