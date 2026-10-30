import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

export const FRONTEND_ROOT = resolve(__dirname, '..')

const SCAN_DIRS = ['app', 'components', 'lib']
const SKIP_DIRS = new Set(['node_modules', '.next'])

function walk(dir: string, acc: string[]): string[] {
  for (const entry of readdirSync(dir)) {
    if (SKIP_DIRS.has(entry)) continue
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) walk(full, acc)
    else if (/\.tsx?$/.test(entry) && !entry.endsWith('.d.ts')) acc.push(full)
  }
  return acc
}

export function sourceFiles(): { path: string; text: string }[] {
  return SCAN_DIRS.flatMap((dir) => walk(join(FRONTEND_ROOT, dir), [])).map((full) => ({
    path: relative(FRONTEND_ROOT, full),
    text: readFileSync(full, 'utf8'),
  }))
}
