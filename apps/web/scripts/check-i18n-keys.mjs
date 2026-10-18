#!/usr/bin/env node
// Fails when a template or component references a literal translation key that is missing
// from packages/i18n/en.json or ar.json (catalogue parity is checked by i18n-completeness.spec.ts;
// this catches keys used in code that were never added to either catalogue).
//
// Dynamic keys built as `'prefix.' + value` are checked against KNOWN_DYNAMIC_SUFFIXES below:
// list every value the backend can send for such a prefix.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const webSrc = join(here, '..', 'src', 'app');
const i18nDir = join(here, '..', '..', '..', 'packages', 'i18n');

const KNOWN_DYNAMIC_SUFFIXES = {
  // ingestion_email_log.match_method check constraint (20260924203652_rfq_reply_match_method.sql)
  'ingestion.emailLog.matchMethods.': ['address', 'domain', 'thread', 'manual', 'rfq_reply'],
};

function leafKeys(obj, prefix = '', out = new Set()) {
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) leafKeys(v, path, out);
    else out.add(path);
  }
  return out;
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(html|ts)$/.test(name) && !/\.spec\.ts$/.test(name)) out.push(p);
  }
  return out;
}

const catalogues = Object.fromEntries(
  ['en', 'ar'].map((l) => [l, leafKeys(JSON.parse(readFileSync(join(i18nDir, `${l}.json`), 'utf8')))])
);

// 'a.b.c' | translate   ·   instant('a.b.c')   ·   get('a.b.c')   ·   stream('a.b.c')
const patterns = [
  /'([a-zA-Z][\w-]*(?:\.[\w-]+)+)'\s*\|\s*translate\b/g,
  /\.(?:instant|get|stream)\(\s*'([a-zA-Z][\w-]*(?:\.[\w-]+)+)'/g,
];
const dynamicPattern = /'([a-zA-Z][\w-]*(?:\.[\w-]+)*\.)'\s*\+/g;

const problems = [];
for (const file of walk(webSrc)) {
  const text = readFileSync(file, 'utf8');
  const rel = relative(join(here, '..'), file);
  for (const re of patterns) {
    for (const m of text.matchAll(re)) {
      const key = m[1];
      for (const [locale, keys] of Object.entries(catalogues)) {
        if (!keys.has(key)) problems.push(`${rel}: '${key}' missing in ${locale}.json`);
      }
    }
  }
  for (const m of text.matchAll(dynamicPattern)) {
    const prefix = m[1];
    const suffixes = KNOWN_DYNAMIC_SUFFIXES[prefix];
    if (!suffixes) continue;
    for (const suffix of suffixes) {
      for (const [locale, keys] of Object.entries(catalogues)) {
        if (!keys.has(prefix + suffix)) {
          problems.push(`${rel}: '${prefix}${suffix}' missing in ${locale}.json`);
        }
      }
    }
  }
}

const unique = [...new Set(problems)];
if (unique.length) {
  console.error(`Missing translation keys (${unique.length}):\n  ${unique.join('\n  ')}`);
  process.exit(1);
}
console.log('i18n keys: every literal key used in apps/web/src/app exists in en and ar.');
