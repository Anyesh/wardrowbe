#!/usr/bin/env node
// Builds messages/en-GB/ from messages/en/. British English is US English with different
// spelling plus a few clothing words, so the catalog is derived rather than translated by
// hand: every en string gets the spelling rules below, then i18n/en-GB-overrides.json
// replaces whole strings where a rule is not enough (Pants -> Trousers, Fall -> Autumn).
// The files are complete copies because request.ts merges a locale over en only at the top
// level of each namespace and i18n:parity requires every key.
//
//   node scripts/gen-en-gb.mjs          write messages/en-GB/
//   node scripts/gen-en-gb.mjs --check  fail if messages/en-GB/ is stale (run by i18n:check)
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE_DIR = join(ROOT, 'messages', 'en');
const TARGET_DIR = join(ROOT, 'messages', 'en-GB');
const OVERRIDES_PATH = join(ROOT, 'i18n', 'en-GB-overrides.json');

// [US stem, British stem]. Matched at the start of a word, case-insensitively, and the
// replacement keeps the source's capitalisation (color -> colour, Color -> Colour).
const SPELLINGS = [
  ['color', 'colour'],
  ['favorite', 'favourite'],
  ['reanalyz', 'reanalys'],
  ['analyz', 'analys'],
  ['personaliz', 'personalis'],
  ['prioritiz', 'prioritis'],
  ['customiz', 'customis'],
  ['gray', 'grey'],
];

// Whole-word clothing terms whose British meaning is unambiguous in a wardrobe app. Words that
// depend on context (vest, fall) are left to en-GB-overrides.json.
const WORDS = [
  ['pants', 'trousers'],
  ['sneakers', 'trainers'],
  ['sneaker', 'trainer'],
  ['sweaters', 'jumpers'],
  ['sweater', 'jumper'],
];

const SPELLING_RE = new RegExp(
  `\\b(${SPELLINGS.map(([us]) => us).join('|')})|\\b(${WORDS.map(([us]) => us).join('|')})\\b`,
  'gi',
);
const BRITISH = new Map([...SPELLINGS, ...WORDS]);

// ICU argument names ({color}, {count, plural, ...}) and select/plural selectors
// (`gray {...}`, `=0 {...}`) are code, not copy, so they are masked before the spelling pass
// and restored after it.
const ARGUMENT_RE = /\{\s*[A-Za-z0-9_]+\s*(?=[,}])|[=A-Za-z0-9_-]+\s*(?=\{)/g;

function matchCase(source, replacement) {
  if (source === source.toUpperCase()) return replacement.toUpperCase();
  if (source[0] === source[0].toUpperCase()) return replacement[0].toUpperCase() + replacement.slice(1);
  return replacement;
}

export function britishSpelling(text) {
  const args = [];
  const masked = text.replace(ARGUMENT_RE, (m) => `\u0000${args.push(m) - 1}\u0000`);
  const converted = masked.replace(SPELLING_RE, (m) => matchCase(m, BRITISH.get(m.toLowerCase())));
  return converted.replace(/\u0000(\d+)\u0000/g, (_, i) => args[Number(i)]);
}

function convert(value) {
  if (typeof value === 'string') return britishSpelling(value);
  if (Array.isArray(value)) return value.map(convert);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, convert(v)]));
  }
  return value;
}

function applyOverride(catalogs, key, text) {
  const [namespace, ...path] = key.split('.');
  let node = catalogs[namespace];
  for (const part of path.slice(0, -1)) node = node?.[part];
  const leaf = path.at(-1);
  if (!node || typeof node[leaf] !== 'string') {
    throw new Error(`en-GB-overrides.json: '${key}' is not a string in messages/en`);
  }
  node[leaf] = text;
}

export function buildCatalogs() {
  const catalogs = {};
  for (const file of readdirSync(SOURCE_DIR).filter((f) => f.endsWith('.json')).sort()) {
    catalogs[file.slice(0, -5)] = convert(JSON.parse(readFileSync(join(SOURCE_DIR, file), 'utf8')));
  }
  const overrides = JSON.parse(readFileSync(OVERRIDES_PATH, 'utf8'));
  for (const [key, text] of Object.entries(overrides)) {
    if (key.startsWith('_')) continue;
    applyOverride(catalogs, key, text);
  }
  return catalogs;
}

function main() {
  const check = process.argv.includes('--check');
  const stale = [];
  if (!check) mkdirSync(TARGET_DIR, { recursive: true });

  const catalogs = buildCatalogs();
  for (const [namespace, catalog] of Object.entries(catalogs)) {
    const path = join(TARGET_DIR, `${namespace}.json`);
    const next = `${JSON.stringify(catalog, null, 2)}\n`;
    if (check) {
      if (!existsSync(path) || readFileSync(path, 'utf8') !== next) stale.push(`${namespace}.json`);
    } else {
      writeFileSync(path, next);
    }
  }

  const expected = new Set(Object.keys(catalogs).map((ns) => `${ns}.json`));
  const leftovers = existsSync(TARGET_DIR)
    ? readdirSync(TARGET_DIR).filter((f) => f.endsWith('.json') && !expected.has(f))
    : [];

  if (check) {
    if (stale.length || leftovers.length) {
      for (const f of stale) console.error(`  messages/en-GB/${f} is out of date`);
      for (const f of leftovers) console.error(`  messages/en-GB/${f} has no en source`);
      console.error('gen-en-gb: FAILED. Run `npm run i18n:en-gb` and commit the result.');
      process.exit(1);
    }
    console.log('gen-en-gb: messages/en-GB is up to date');
  } else {
    if (leftovers.length) {
      console.warn(`gen-en-gb: no en source for ${leftovers.join(', ')} - delete them by hand`);
    }
    console.log(`gen-en-gb: wrote ${Object.keys(catalogs).length} files to messages/en-GB`);
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
