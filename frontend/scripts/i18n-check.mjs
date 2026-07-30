#!/usr/bin/env node
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const MESSAGES_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'messages');
const SOURCE_LOCALE = 'en';

function flatten(obj, prefix = '') {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) Object.assign(out, flatten(v, path));
    else out[path] = v;
  }
  return out;
}

function loadLocale(locale) {
  const dir = join(MESSAGES_DIR, locale);
  const flat = {};
  for (const file of readdirSync(dir).filter((f) => f.endsWith('.json')).sort()) {
    const ns = file.slice(0, -5);
    const parsed = JSON.parse(readFileSync(join(dir, file), 'utf8'));
    for (const [k, v] of Object.entries(flatten(parsed))) flat[`${ns}.${k}`] = v;
  }
  return flat;
}

// Matches {name}, {count, plural, ...}, {when, date, ...}. Deliberately not a full ICU parser:
// it only needs to catch placeholder drift between a source string and its translations.
function placeholders(value) {
  if (typeof value !== 'string') return new Set();
  return new Set([...value.matchAll(/\{\s*([a-zA-Z0-9_]+)\s*[,}]/g)].map((m) => m[1]));
}

function balanced(value) {
  if (typeof value !== 'string') return true;
  let depth = 0;
  for (const ch of value) {
    if (ch === '{') depth++;
    else if (ch === '}') depth--;
    if (depth < 0) return false;
  }
  return depth === 0;
}

const locales = readdirSync(MESSAGES_DIR).filter((d) => statSync(join(MESSAGES_DIR, d)).isDirectory()).sort();

if (!locales.includes(SOURCE_LOCALE)) {
  console.error(`i18n-check: no '${SOURCE_LOCALE}' directory in ${MESSAGES_DIR}`);
  process.exit(1);
}

const source = loadLocale(SOURCE_LOCALE);
const sourceKeys = new Set(Object.keys(source));
const problems = [];

for (const key of sourceKeys) {
  if (!balanced(source[key])) problems.push(`${SOURCE_LOCALE}: unbalanced braces in '${key}'`);
  if (typeof source[key] !== 'string') problems.push(`${SOURCE_LOCALE}: '${key}' is not a string`);
  if (source[key] === '') problems.push(`${SOURCE_LOCALE}: '${key}' is empty`);
}

for (const locale of locales) {
  if (locale === SOURCE_LOCALE) continue;
  const target = loadLocale(locale);
  const targetKeys = new Set(Object.keys(target));

  for (const key of sourceKeys) {
    if (!targetKeys.has(key)) {
      problems.push(`${locale}: missing '${key}'`);
      continue;
    }
    if (typeof target[key] !== 'string' || target[key] === '') {
      problems.push(`${locale}: '${key}' is empty or not a string`);
      continue;
    }
    if (!balanced(target[key])) {
      problems.push(`${locale}: unbalanced braces in '${key}'`);
      continue;
    }
    const want = placeholders(source[key]);
    const got = placeholders(target[key]);
    for (const p of want) if (!got.has(p)) problems.push(`${locale}: '${key}' drops placeholder {${p}}`);
    for (const p of got) if (!want.has(p)) problems.push(`${locale}: '${key}' adds unknown placeholder {${p}}`);
  }

  for (const key of targetKeys) if (!sourceKeys.has(key)) problems.push(`${locale}: extra key '${key}' not in ${SOURCE_LOCALE}`);
}

console.log(`i18n-check: ${locales.length} locales [${locales.join(', ')}], ${sourceKeys.size} keys in ${SOURCE_LOCALE}`);

if (problems.length) {
  const shown = problems.slice(0, 60);
  for (const p of shown) console.error(`  ${p}`);
  if (problems.length > shown.length) console.error(`  ... and ${problems.length - shown.length} more`);
  console.error(`i18n-check: FAILED with ${problems.length} problem(s)`);
  process.exit(1);
}

console.log('i18n-check: OK');
