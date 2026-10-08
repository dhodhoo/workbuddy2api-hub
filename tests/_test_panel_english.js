/* The panel is English only - this suite is what keeps it that way.
 *
 * dashboard.html used to carry a runtime translator (DICT + RULES + a DOM
 * walker, added in #134) that flipped the page between Chinese and English.
 * The panel now ships one language: the copy is English in the source, the
 * translator and its toggle are gone, and the only Chinese left in the file is
 * inside comments.
 *
 * The rule is checked from both directions so it cannot rot:
 *
 *   1. no Han character may reach the page - not in markup text, not in an
 *      i18n attribute, not in an inline handler, not in a script string
 *      literal (the runtime-injected copy is the one most easily forgotten);
 *   2. the translator must stay gone - a reintroduced `DICT`, `WB_I18N` or
 *      language toggle would silently make (1) meaningless.
 *
 * Comments are skipped: they never render, and the repo writes them in
 * Chinese. Run with Node:
 *
 *     node tests/_test_panel_english.js
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'dashboard.html'), 'utf8');
const HAN = /[\u4e00-\u9fff]/;

// ------------------------------------------------------------- no translator
for (const relic of ['WB_I18N', 'var DICT = {', 'var RULES = [', 'LANG_KEY',
                     'data-no-i18n', 'lang-btn', 'toggleLang', 'selectLang']) {
  assert.ok(!html.includes(relic),
    `dashboard.html still carries the language switch (${relic}); the panel is English only`);
}

// ------------------------------------------------------------ candidate copy
// Every place a string reaches the rendered page, read the way the browser
// reads it: entities decoded in markup, escapes decoded in script strings,
// comments skipped.

const ENTITIES = {
  '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'",
  '&apos;': "'", '&nbsp;': '\u00a0', '&mdash;': '\u2014', '&hellip;': '\u2026',
  '&times;': '\u00d7', '&middot;': '\u00b7', '&rarr;': '\u2192', '&larr;': '\u2190',
};
const decodeEntities = t => t.replace(/&(?:amp|lt|gt|quot|#39|apos|nbsp|mdash|hellip|times|middot|rarr|larr);/g,
  m => ENTITIES[m] !== undefined ? ENTITIES[m] : m);

function decodeEscapes(raw) {
  return raw.replace(/\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)/g, (m, esc) => {
    if (esc[0] === 'u' || esc[0] === 'x') return String.fromCharCode(parseInt(esc.slice(1), 16));
    if (esc === 'n') return '\n';
    if (esc === 'r') return '\r';
    if (esc === 't') return '\t';
    if (esc === 'b') return '\b';
    if (esc === 'f') return '\f';
    if (esc === 'v') return '\v';
    return esc;
  });
}

/* String literals in a script block, comments skipped. A template literal is
 * cut at each ${...}: only its static parts reach the DOM verbatim. */
function scanScriptStrings(source) {
  const out = [];
  let i = 0;
  while (i < source.length) {
    const ch = source[i];
    if (ch === '/' && source[i + 1] === '/') { const nl = source.indexOf('\n', i); i = nl < 0 ? source.length : nl; continue; }
    if (ch === '/' && source[i + 1] === '*') { const end = source.indexOf('*/', i + 2); i = end < 0 ? source.length : end + 2; continue; }
    if (ch !== '"' && ch !== "'" && ch !== '`') { i++; continue; }
    const quote = ch;
    i++;
    let segment = '';
    while (i < source.length) {
      const c = source[i];
      if (c === '\\') { segment += c + (source[i + 1] || ''); i += 2; continue; }
      if (c === quote) { i++; break; }
      if (quote === '`' && c === '$' && source[i + 1] === '{') {
        if (segment) out.push(segment);
        segment = '';
        let depth = 1;
        i += 2;
        while (i < source.length && depth > 0) {
          if (source[i] === '{') depth++;
          else if (source[i] === '}') depth--;
          i++;
        }
        continue;
      }
      if (c === '\n' && quote !== '`') break;   // unterminated literal
      segment += c;
      i++;
    }
    if (segment) out.push(segment);
  }
  return out;
}

const offenders = [];
const lineOf = idx => html.slice(0, idx).split('\n').length;
const seen = new Set();
function check(where, idx, text) {
  const decoded = decodeEscapes(decodeEntities(String(text)));
  if (!HAN.test(decoded)) return;
  const key = lineOf(idx) + '\u0000' + decoded;
  if (seen.has(key)) return;
  seen.add(key);
  offenders.push({ line: lineOf(idx), where, text: decoded.replace(/\s+/g, ' ').trim() });
}

// Ranges that are not copy: comments, <script>/<style> bodies (scanned
// separately as literals), and the contents of HTML comments.
const zones = [];
for (const m of html.matchAll(/<script[^>]*>[\s\S]*?<\/script>/g)) zones.push([m.index, m.index + m[0].length]);
for (const m of html.matchAll(/<style[^>]*>[\s\S]*?<\/style>/g)) zones.push([m.index, m.index + m[0].length]);
for (const m of html.matchAll(/<!--[\s\S]*?-->/g)) zones.push([m.index, m.index + m[0].length]);
const inZone = idx => zones.some(([a, b]) => idx >= a && idx < b);

// 1) markup text nodes
for (const m of html.matchAll(/>([^<>]*[\u4e00-\u9fff][^<>]*)</g)) {
  if (!inZone(m.index)) check('markup text', m.index + 1, m[1]);
}

// 2) the attributes a user actually reads
const attrsMatch = /var ATTRS = \[([^\]]*)\]/.exec(html);
const ATTRS = attrsMatch
  ? attrsMatch[1].split(',').map(s => s.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean)
  : ['title', 'placeholder', 'aria-label', 'data-label', 'alt'];
const attrRe = new RegExp('(?:' + ATTRS.join('|') + ')="([^"]*[\\u4e00-\\u9fff][^"]*)"', 'g');
for (const m of html.matchAll(attrRe)) {
  if (!inZone(m.index)) check('@' + m[0].split('=')[0], m.index, m[1]);
}

// 3) inline handlers - the copy a handler builds only exists after it runs
for (const m of html.matchAll(/\son[a-z]+\s*=\s*"([^"]*)"/g)) {
  if (inZone(m.index)) continue;
  for (const lit of scanScriptStrings(decodeEntities(m[1]))) check('inline handler', m.index, lit);
}

// 4) script string literals
for (const m of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)) {
  for (const lit of scanScriptStrings(m[1])) check('script literal', m.index, lit);
}

if (offenders.length) {
  const report = offenders.map(o => `  L${o.line} [${o.where}] ${JSON.stringify(o.text)}`);
  assert.fail(`${offenders.length} Chinese string(s) still reach the panel:\n` + report.join('\n'));
}

// ---------------------------------------------------------- no glued words
// The panel used to translate itself string by string, and a heading built from
// fragments came out as "CurrentDisableAccountsandModel" - no Chinese left, so
// the check above passed while the page read as nonsense. The copy is written
// in the source now, so a word like that can only be a typo or a bad merge; the
// product names below are the only camelCase the page is allowed to contain.
const PRODUCT_NAMES = /^(WorkBuddy|OpenRouter|DeepSeek|DuckDuckGo|GitHub|CodeBuddy|VSCode|JavaScript|TypeScript|PowerShell|LaTeX|OpenAI|ChatGPT)$/;
const glued = [];
for (const m of html.matchAll(/>([^<>]*[A-Za-z][^<>]*)</g)) {
  if (inZone(m.index)) continue;
  const text = m[1].replace(/\s+/g, ' ').trim();
  for (const word of text.match(/[A-Za-z]{5,}/g) || []) {
    if (/[a-z][A-Z]/.test(word) && !PRODUCT_NAMES.test(word)) {
      glued.push(`  L${lineOf(m.index)} ${JSON.stringify(word)} in ${JSON.stringify(text.slice(0, 70))}`);
    }
  }
}
for (const m of html.matchAll(attrRe)) {
  if (inZone(m.index)) continue;
  for (const word of decodeEntities(m[1]).match(/[A-Za-z]{5,}/g) || []) {
    if (/[a-z][A-Z]/.test(word) && !PRODUCT_NAMES.test(word)) {
      glued.push(`  L${lineOf(m.index)} ${JSON.stringify(word)} in @${m[0].split('=')[0]}`);
    }
  }
}
assert.deepStrictEqual(glued, [],
  'words glued together in panel copy:\n' + glued.join('\n'));

console.log('panel English OK: 0 Chinese strings outside comments, 0 glued words');
