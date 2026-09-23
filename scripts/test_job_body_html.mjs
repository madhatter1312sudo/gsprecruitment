#!/usr/bin/env node
/**
 * issue #153 verification: exercises website/vacature.js's
 * buildJobBodyHtml() against fixture jobs and asserts:
 *   - a job with an English text renders that English text under the
 *     English heading, and its Dutch text under the Dutch heading
 *     (acceptance criterion 3);
 *   - a job with no English text never renders a Dutch sentence,
 *     unmarked, under an English heading -- it gets the visibly marked
 *     fallback instead (acceptance criterion 4);
 *   - a section with neither language's text is not rendered at all;
 *   - values are HTML-escaped (GSP.esc), matching every other job.*
 *     interpolation in this file.
 *
 * Requires website/gsp-util.js to run first (defines global.GSP), the
 * same load order vacature.html uses for the browser.
 *
 * Usage: node scripts/test_job_body_html.mjs
 * Exits non-zero on any assertion failure.
 */
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// gsp-util.js's IIFE runs as `(function (global) {...})(... : this)`; under
// CommonJS, a required module's top-level `this` is `module.exports`, so
// its `global.GSP = ...` assignments land on that exports object -- expose
// them on the real global here, the same object vacature.js's unqualified
// `GSP.esc(...)` calls resolve against (matching the browser, where
// gsp-util.js's <script> tag runs before vacature.js's and both share
// `window`).
const { GSP } = require(path.join(__dirname, '..', 'website', 'gsp-util.js'));
global.GSP = GSP;
const { buildJobBodyHtml } = require(path.join(__dirname, '..', 'website', 'vacature.js'));

let failures = 0;
function assert(cond, msg) {
  if (!cond) {
    failures++;
    console.error(`  FAIL: ${msg}`);
  }
}
function ok(msg) {
  console.log(`  ok: ${msg}`);
}

console.log('Fixture 1: description + requirements + nice_to_have all have an English twin');
{
  const job = {
    description: 'Wij zoeken een embedded software engineer.',
    description_en: 'We are looking for an embedded software engineer.',
    requirements: 'Minimaal 5 jaar ervaring met C++.',
    requirements_en: 'At least 5 years of C++ experience.',
    nice_to_have: 'Kennis van Rust is een pre.',
    nice_to_have_en: 'Rust knowledge is a plus.',
  };
  const html = buildJobBodyHtml(job);
  assert(html.includes('<h2 class="lang-en">About the role</h2>'), 'fixture1: English heading present');
  assert(html.includes('<p class="lang-en">We are looking for an embedded software engineer.</p>'), 'fixture1: English description rendered under English heading');
  assert(html.includes('<p class="lang-nl">Wij zoeken een embedded software engineer.</p>'), 'fixture1: Dutch description rendered under Dutch heading');
  assert(html.includes('<p class="lang-en">At least 5 years of C++ experience.</p>'), 'fixture1: English requirements rendered');
  assert(html.includes('<p class="lang-en">Rust knowledge is a plus.</p>'), 'fixture1: English nice_to_have rendered');
  assert(!html.includes('gsp-lang-fallback'), 'fixture1: no fallback marker when every English field is present');
  ok('fixture1 passed');
}

console.log('\nFixture 2: no English text anywhere (today\'s 27 pool vacancies)');
{
  const job = {
    description: 'Wij zoeken een embedded software engineer.',
    requirements: 'Minimaal 5 jaar ervaring met C++.',
    nice_to_have: 'Kennis van Rust is een pre.',
  };
  const html = buildJobBodyHtml(job);
  // The defect this issue fixes: the Dutch sentence must never appear
  // inside the <p class="lang-en"> paragraph, unmarked.
  assert(!/<p class="lang-en">Wij zoeken een embedded software engineer\.<\/p>/.test(html), 'fixture2: Dutch description text never rendered unmarked inside a lang-en paragraph');
  assert(!/<p class="lang-en">Minimaal 5 jaar ervaring met C\+\+\.<\/p>/.test(html), 'fixture2: Dutch requirements text never rendered unmarked inside a lang-en paragraph');
  assert((html.match(/gsp-lang-fallback/g) || []).length === 3, 'fixture2: all three sections get the visible fallback marker');
  assert(html.includes('<p class="lang-en gsp-lang-fallback">Only available in Dutch.</p>'), 'fixture2: English fallback text present and marked');
  assert(html.includes('<h2 class="lang-en">About the role</h2>'), 'fixture2: English heading still present (marked fallback, not hidden)');
  assert(html.includes('<p class="lang-nl">Wij zoeken een embedded software engineer.</p>'), 'fixture2: Dutch text still renders normally under the Dutch heading');
  ok('fixture2 passed');
}

console.log('\nFixture 3: a section with neither language is skipped entirely');
{
  const job = {
    description: 'Wij zoeken een embedded software engineer.',
    // requirements / nice_to_have both absent
  };
  const html = buildJobBodyHtml(job);
  assert(!html.includes("What we're looking for"), 'fixture3: requirements heading absent when there is no text in either language');
  assert(!html.includes('Nice to have'), 'fixture3: nice_to_have heading absent when there is no text in either language');
  ok('fixture3 passed');
}

console.log('\nFixture 4: HTML in job text is escaped');
{
  const job = {
    description: 'NL <script>alert(1)</script>',
    description_en: 'EN <img src=x onerror=alert(1)>',
  };
  const html = buildJobBodyHtml(job);
  assert(!html.includes('<script>alert(1)</script>'), 'fixture4: Dutch text is escaped');
  assert(!html.includes('<img src=x onerror=alert(1)>'), 'fixture4: English text is escaped');
  assert(html.includes('&lt;script&gt;'), 'fixture4: Dutch escaping produces &lt;script&gt;');
  assert(html.includes('&lt;img'), 'fixture4: English escaping produces &lt;img');
  ok('fixture4 passed');
}

console.log('\nFixture 5: empty job renders nothing');
{
  assert(buildJobBodyHtml({}) === '', 'fixture5: no sections, no output');
  ok('fixture5 passed');
}

console.log(`\n${failures === 0 ? 'PASS' : 'FAIL'}: ${failures} assertion failure(s).`);
process.exit(failures === 0 ? 0 : 1);
