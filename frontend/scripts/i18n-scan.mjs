#!/usr/bin/env node
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SCAN_DIRS = ['app', 'components', 'lib'];

// components/ui holds unmodified shadcn primitives; their strings are structural, not product copy.
const SKIP_DIRS = new Set(['node_modules', '.next', 'components/ui']);
const SKIP_FILES = new Set(['app/layout.tsx', 'app/providers.tsx']);

const TEXT_ATTRS = new Set(['placeholder', 'title', 'aria-label', 'alt', 'label', 'aria-description']);
const TOAST_METHODS = new Set(['success', 'error', 'info', 'warning', 'message', 'loading']);

// A literal is product copy if it reads like a sentence or label rather than an identifier,
// css class, url, mime type, or format token.
const NOT_COPY = [
  /^[a-z0-9]+([-_:/][a-z0-9]+)*$/,
  /^https?:\/\//,
  /^[/#.]/,
  /^[A-Z0-9_]+$/,
  /^\d/,
  /^[^\p{L}]*$/u,
  /^(image|video|audio|application|text)\//,
  /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i,
];

// The product name is a proper noun and stays identical in every locale.
const BRAND = new Set(['Wardrowbe', 'wardrowbe']);

function isCopy(raw) {
  // &ldquo; &rarr; &#8212; are typographic punctuation, not translatable copy, but their
  // entity names are all letters, so they have to go before the letter test.
  const s = raw.replace(/&(?:[a-zA-Z]+|#\d+);/g, '').trim();
  if (s.length < 2) return false;
  if (!/\p{L}\p{L}/u.test(s)) return false;
  if (BRAND.has(s)) return false;
  return !NOT_COPY.some((re) => re.test(s));
}

function walk(dir, acc = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const rel = relative(ROOT, full);
    if (SKIP_DIRS.has(entry) || SKIP_DIRS.has(rel)) continue;
    if (statSync(full).isDirectory()) walk(full, acc);
    else if (/\.tsx?$/.test(entry) && !/\.d\.ts$/.test(entry)) acc.push(full);
  }
  return acc;
}

const findings = [];

for (const file of SCAN_DIRS.flatMap((d) => walk(join(ROOT, d)))) {
  const rel = relative(ROOT, file);
  if (SKIP_FILES.has(rel)) continue;
  const text = readFileSync(file, 'utf8');
  // Parsing a .ts file as TSX makes the parser read generics like `<T>(x: T)` as JSX elements,
  // so every type parameter turns into a bogus jsx-text finding.
  const kind = file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);

  const report = (node, kind, value) => {
    const { line } = sf.getLineAndCharacterOfPosition(node.getStart(sf));
    findings.push({ file: rel, line: line + 1, kind, value: value.trim().replace(/\s+/g, ' ').slice(0, 80) });
  };

  const visit = (node) => {
    if (ts.isJsxText(node) && isCopy(node.text)) report(node, 'jsx-text', node.text);

    if (ts.isJsxAttribute(node) && node.name && TEXT_ATTRS.has(node.name.getText(sf))) {
      const init = node.initializer;
      if (init && ts.isStringLiteral(init) && isCopy(init.text)) report(node, `attr:${node.name.getText(sf)}`, init.text);
      if (init && ts.isJsxExpression(init) && init.expression && ts.isStringLiteral(init.expression) && isCopy(init.expression.text))
        report(node, `attr:${node.name.getText(sf)}`, init.expression.text);
    }

    if (ts.isCallExpression(node)) {
      const callee = node.expression;
      const isToast =
        (ts.isPropertyAccessExpression(callee) &&
          callee.expression.getText(sf) === 'toast' &&
          TOAST_METHODS.has(callee.name.getText(sf))) ||
        (ts.isIdentifier(callee) && callee.text === 'toast');
      if (isToast) {
        const arg = node.arguments[0];
        if (arg && ts.isStringLiteral(arg) && isCopy(arg.text)) report(node, 'toast', arg.text);
        if (arg && ts.isTemplateExpression(arg)) {
          const literal = arg.head.text + arg.templateSpans.map((s) => s.literal.text).join(' ');
          if (isCopy(literal)) report(node, 'toast-template', literal);
        }
      }
    }

    ts.forEachChild(node, visit);
  };

  visit(sf);
}

if (!findings.length) {
  console.log('i18n-scan: OK, no untranslated user-facing strings found');
  process.exit(0);
}

const byFile = findings.reduce((m, f) => ((m[f.file] ??= []).push(f), m), {});
for (const [file, items] of Object.entries(byFile).sort()) {
  console.error(`\n${file}`);
  for (const i of items) console.error(`  ${String(i.line).padStart(4)}  ${i.kind.padEnd(18)} ${JSON.stringify(i.value)}`);
}
console.error(`\ni18n-scan: FAILED, ${findings.length} untranslated string(s) in ${Object.keys(byFile).length} file(s)`);
process.exit(1);
