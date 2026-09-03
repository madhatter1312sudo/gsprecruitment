#!/usr/bin/env node
/**
 * test_render_js.mjs — unit tests for website/admin/js/render.js.
 *
 * Runs gsp-util.js and render.js as plain scripts inside a vm context whose
 * `window` is the context's global object itself (so `window.GSP = ...`
 * really does attach to the shared context, exactly like two <script> tags
 * loaded in a browser in that order). No DOM/browser APIs are exercised —
 * only GSP.esc, GSP.html, GSP.raw and GSP.mount.
 *
 * Usage: node scripts/test_render_js.mjs
 * Exit code 0 = all assertions passed, 1 = at least one failure.
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const context = {};
context.window = context; // window === the vm context's global object
vm.createContext(context);

function load(relPath) {
  const src = fs.readFileSync(path.join(ROOT, relPath), 'utf8');
  vm.runInContext(src, context, { filename: relPath });
}

load('website/gsp-util.js');
load('website/admin/js/render.js');

const { GSP } = context;
const { html, raw, mount } = GSP;

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`  ok — ${name}`);
  } catch (err) {
    failed++;
    console.error(`  FAIL — ${name}`);
    console.error(`    ${err.message}`);
  }
}

function val(result) {
  return String(result);
}

console.log('render.js unit tests\n');

test('plain string interpolation is escaped', () => {
  const r = html`<div>${'<b>hi</b>'}</div>`;
  assert.equal(val(r), '<div>&lt;b&gt;hi&lt;/b&gt;</div>');
});

test('script-tag injection is neutralised', () => {
  const evil = '<script>alert(1)</script>';
  const r = html`<td>${evil}</td>`;
  assert.equal(val(r), '<td>&lt;script&gt;alert(1)&lt;/script&gt;</td>');
  assert.ok(!val(r).includes('<script>'), 'must not contain a live <script> tag');
});

test('double and single quotes are escaped (attribute-breakout safe)', () => {
  const name = `foo" onmouseover="alert(1)" x='y`;
  const r = html`<input value="${name}">`;
  assert.equal(val(r), '<input value="foo&quot; onmouseover=&quot;alert(1)&quot; x=&#39;y">');
  assert.ok(!val(r).includes('onmouseover="alert'), 'must not break out of the attribute');
});

test('backtick is escaped too (defense-in-depth, matches GSP.esc)', () => {
  const r = html`<div>${'a`b'}</div>`;
  assert.equal(val(r), '<div>a&#96;b</div>');
});

test('numbers interpolate as their string form, unescaped-looking but safe', () => {
  const r = html`<td>${42}</td><td>${0}</td>`;
  assert.equal(val(r), '<td>42</td><td>0</td>');
});

test('null and undefined interpolate to empty string', () => {
  const r = html`<td>${null}</td><td>${undefined}</td>`;
  assert.equal(val(r), '<td></td><td></td>');
});

test('a flat array of strings is escaped element-by-element and joined', () => {
  const r = html`<ul>${['<a>', '<b>']}</ul>`;
  assert.equal(val(r), '<ul>&lt;a&gt;&lt;b&gt;</ul>');
});

test('nested array of html`` results (row list -> tbody) composes correctly', () => {
  const rows = [
    { name: 'Alice', note: '<safe>' },
    { name: '<script>evil()</script>', note: 'fine' },
  ];
  const tbody = html`<tbody>${rows.map(r => html`<tr><td>${r.name}</td><td>${r.note}</td></tr>`)}</tbody>`;
  assert.equal(
    val(tbody),
    '<tbody><tr><td>Alice</td><td>&lt;safe&gt;</td></tr>' +
    '<tr><td>&lt;script&gt;evil()&lt;/script&gt;</td><td>fine</td></tr></tbody>'
  );
});

test('deeply nested html`` calls all still auto-escape their own leaves', () => {
  const inner = html`<span>${'<i>x</i>'}</span>`;
  const outer = html`<div>${inner}</div>`;
  assert.equal(val(outer), '<div><span>&lt;i&gt;x&lt;/i&gt;</span></div>');
});

test('raw() inserts a pre-built safe fragment verbatim', () => {
  const icon = raw('<i class="fa-solid fa-star"></i>');
  const r = html`<button>${icon} Save</button>`;
  assert.equal(val(r), '<button><i class="fa-solid fa-star"></i> Save</button>');
});

test('raw() over an array of html``/string fragments joins them unescaped', () => {
  const parts = raw([html`<b>A</b>`, '<i>B</i>']);
  const r = html`<div>${parts}</div>`;
  assert.equal(val(r), '<div><b>A</b><i>B</i></div>');
});

test('raw() does NOT retroactively unescape a value that was already escaped', () => {
  // raw() only skips escaping for the value it wraps directly — it must
  // never be used to "unwrap" untrusted text; this just documents that a
  // plain (non-html``) string handed to raw() is inserted as-is, so callers
  // are responsible for only ever wrapping their own trusted markup.
  const trusted = raw('<span class="badge">ok</span>');
  const r = html`<td>${trusted}</td>`;
  assert.equal(val(r), '<td><span class="badge">ok</span></td>');
});

test('a conditional branch (ternary) returning "" or an html`` fragment composes', () => {
  const editable = false;
  const r = html`<div>${editable ? html`<button>Edit</button>` : ''}</div>`;
  assert.equal(val(r), '<div></div>');
});

test('mount() sets el.innerHTML from an html`` result', () => {
  let written = null;
  const fakeEl = { set innerHTML(v) { written = v; }, get innerHTML() { return written; } };
  mount(fakeEl, html`<p>${'<hi>'}</p>`);
  assert.equal(written, '<p>&lt;hi&gt;</p>');
});

test('mount() on a null element is a safe no-op', () => {
  assert.doesNotThrow(() => mount(null, html`<p>x</p>`));
  assert.doesNotThrow(() => mount(undefined, html`<p>x</p>`));
});

test('mount() accepts raw() results too', () => {
  let written = null;
  const fakeEl = { set innerHTML(v) { written = v; }, get innerHTML() { return written; } };
  mount(fakeEl, raw('<p>static</p>'));
  assert.equal(written, '<p>static</p>');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
