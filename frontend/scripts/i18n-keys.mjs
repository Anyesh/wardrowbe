#!/usr/bin/env node
// Resolves every t('...') call site against the en catalog. Missing keys are invisible to
// tsc, eslint and vitest because t() takes a plain string, so they only surface as raw key
// paths at render time. This is the gate that catches them.
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const MESSAGES = join(ROOT, 'messages');
const SCAN_DIRS = ['app', 'components', 'lib'];
const SKIP = new Set(['node_modules', '.next']);

function flatten(obj, prefix = '') {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) Object.assign(out, flatten(v, path));
    else out[path] = v;
  }
  return out;
}

function loadEnglish() {
  const dir = join(MESSAGES, 'en');
  if (existsSync(dir) && statSync(dir).isDirectory()) {
    const flat = {};
    for (const f of readdirSync(dir).filter((f) => f.endsWith('.json'))) {
      const ns = f.slice(0, -5);
      for (const [k, v] of Object.entries(flatten(JSON.parse(readFileSync(join(dir, f), 'utf8'))))) flat[`${ns}.${k}`] = v;
    }
    return flat;
  }
  return flatten(JSON.parse(readFileSync(join(MESSAGES, 'en.json'), 'utf8')));
}

function walk(dir, acc = []) {
  for (const entry of readdirSync(dir)) {
    if (SKIP.has(entry)) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, acc);
    else if (/\.tsx?$/.test(entry) && !/\.d\.ts$/.test(entry)) acc.push(full);
  }
  return acc;
}

// A helper that receives `t` as a parameter, e.g. formatWornAgo(date, t), gets its namespace from
// whichever caller passes it, so the key it builds cannot be resolved statically. Reporting those
// would be a false positive, so they are skipped.
function isShadowedByParameter(node, name) {
  for (let cur = node.parent; cur; cur = cur.parent) {
    if (
      ts.isFunctionDeclaration(cur) ||
      ts.isFunctionExpression(cur) ||
      ts.isArrowFunction(cur) ||
      ts.isMethodDeclaration(cur)
    ) {
      if (cur.parameters.some((p) => ts.isIdentifier(p.name) && p.name.text === name)) return true;
    }
  }
  return false;
}

const english = loadEnglish();
const catalogKeys = new Set(Object.keys(english));
// A namespace is also a valid target: t.rich / nested access resolve against a subtree.
const namespacePrefixes = new Set();
for (const k of catalogKeys) {
  const parts = k.split('.');
  for (let i = 1; i < parts.length; i++) namespacePrefixes.add(parts.slice(0, i).join('.'));
}

const unresolved = [];
const used = new Set();

for (const file of SCAN_DIRS.flatMap((d) => walk(join(ROOT, d)))) {
  const rel = relative(ROOT, file);
  const text = readFileSync(file, 'utf8');
  const kind = file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);

  // varName -> [{ ns, pos }], resolved by nearest preceding declaration so that several
  // components in one file can each hold their own useTranslations namespace.
  const bindings = new Map();
  const calls = [];

  const visit = (node) => {
    if (
      ts.isVariableDeclaration(node) &&
      node.initializer &&
      ts.isCallExpression(node.initializer) &&
      /^(useTranslations|getTranslations)$/.test(node.initializer.expression.getText(sf)) &&
      ts.isIdentifier(node.name)
    ) {
      const arg = node.initializer.arguments[0];
      const ns = arg && ts.isStringLiteral(arg) ? arg.text : '';
      if (!bindings.has(node.name.text)) bindings.set(node.name.text, []);
      bindings.get(node.name.text).push({ ns, pos: node.getStart(sf) });
    }

    if (ts.isCallExpression(node)) {
      let callee = node.expression;
      // t('key') and t.rich('key') / t.markup('key') both resolve the same way.
      if (ts.isPropertyAccessExpression(callee) && /^(rich|markup|raw|has)$/.test(callee.name.getText(sf))) callee = callee.expression;
      if (ts.isIdentifier(callee)) {
        const arg = node.arguments[0];
        if (arg && ts.isStringLiteral(arg) && !isShadowedByParameter(node, callee.text)) {
          calls.push({ name: callee.text, key: arg.text, pos: node.getStart(sf) });
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);

  for (const call of calls) {
    const decls = bindings.get(call.name);
    if (!decls) continue;
    const applicable = decls.filter((d) => d.pos < call.pos);
    const decl = applicable.length ? applicable[applicable.length - 1] : decls[0];
    const full = decl.ns ? `${decl.ns}.${call.key}` : call.key;
    used.add(full);
    if (!catalogKeys.has(full) && !namespacePrefixes.has(full)) {
      const { line } = sf.getLineAndCharacterOfPosition(call.pos);
      unresolved.push({ file: rel, line: line + 1, key: full });
    }
  }
}

const orphans = [...catalogKeys].filter((k) => !used.has(k) && ![...used].some((u) => u.startsWith(k + '.')));

console.log(`i18n-keys: ${catalogKeys.size} keys in catalog, ${used.size} referenced from source`);

if (process.argv.includes('--orphans') && orphans.length) {
  console.log(`\n${orphans.length} catalog key(s) never referenced from source:`);
  for (const k of orphans.sort()) console.log(`  ${k}`);
}

if (unresolved.length) {
  const byFile = unresolved.reduce((m, u) => ((m[u.file] ??= []).push(u), m), {});
  for (const [file, items] of Object.entries(byFile).sort()) {
    console.error(`\n${file}`);
    for (const i of items) console.error(`  ${String(i.line).padStart(4)}  ${i.key}`);
  }
  console.error(`\ni18n-keys: FAILED, ${unresolved.length} t() call(s) reference keys absent from the en catalog`);
  process.exit(1);
}

console.log('i18n-keys: OK, every t() call resolves');
