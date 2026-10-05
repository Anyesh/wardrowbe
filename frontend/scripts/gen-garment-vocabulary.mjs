#!/usr/bin/env node
// Writes lib/generated/garment-vocabulary.ts from the backend vocabulary file, which is the only
// place garment types, roles, materials and formality levels are edited by hand. Run with --check
// to fail when the committed output is stale. It reads ../backend, which is outside the frontend
// Docker build context, so it must never run from build or prebuild.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE = resolve(ROOT, '..', 'backend', 'app', 'data', 'garment_vocabulary.json');
const OUTPUT = resolve(ROOT, 'lib', 'generated', 'garment-vocabulary.ts');

const quote = (value) => `'${value}'`;
const key = (value) => (/^[A-Za-z_][A-Za-z0-9_]*$/.test(value) ? value : quote(value));
const list = (values) => `[${values.map(quote).join(', ')}] as const`;

function render({ types, materials, formality }) {
  const roles = types.map(({ value, role }) => `  ${key(value)}: ${quote(role)},`).join('\n');
  return [
    '// Generated from backend/app/data/garment_vocabulary.json by scripts/gen-garment-vocabulary.mjs.',
    '// Do not edit by hand; run `corepack pnpm run vocab:gen`.',
    `export const CLOTHING_TYPE_VALUES = ${list(types.map((t) => t.value))};`,
    `export const MATERIAL_VALUES = ${list(materials)};`,
    `export const FORMALITY_VALUES = ${list(formality)};`,
    '',
    'export const ITEM_ROLE: Record<string, string> = {',
    roles,
    '};',
    '',
  ].join('\n');
}

const expected = render(JSON.parse(readFileSync(SOURCE, 'utf8')));

if (process.argv.includes('--check')) {
  const current = existsSync(OUTPUT) ? readFileSync(OUTPUT, 'utf8') : null;
  if (current !== expected) {
    console.error('garment-vocabulary.ts is out of date with backend/app/data/garment_vocabulary.json; run `corepack pnpm run vocab:gen`.');
    process.exit(1);
  }
  console.log('vocab-check: OK');
} else {
  mkdirSync(dirname(OUTPUT), { recursive: true });
  writeFileSync(OUTPUT, expected);
  console.log(`Wrote ${OUTPUT}`);
}
