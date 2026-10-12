// @vitest-environment node
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import en from '@/messages/en/errors.json'

const BACKEND_APP = resolve(__dirname, '..', '..', 'backend', 'app')

// Matches the three ways the backend names a code: a detail dict, CodedHTTPException's second
// positional argument, and RecommendationInputError's first.
const CODE_PATTERNS = [
  /"error_code":\s*"([A-Z_]+)"/g,
  /CodedHTTPException\(\s*[^,()]+,\s*"([A-Z_]+)"/g,
  /RecommendationInputError\(\s*"([A-Z_]+)"/g,
]

function pythonFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return pythonFiles(full)
    return entry.endsWith('.py') ? [full] : []
  })
}

function backendCodes(): Set<string> {
  const codes = new Set<string>()
  for (const file of pythonFiles(BACKEND_APP)) {
    const source = readFileSync(file, 'utf8')
    for (const pattern of CODE_PATTERNS) for (const match of Array.from(source.matchAll(pattern))) codes.add(match[1])
  }
  return codes
}

describe('backend error codes', () => {
  it('finds the codes it is meant to check', () => {
    expect(backendCodes()).toContain('RATE_LIMITED')
    expect(backendCodes()).toContain('LOCATION_NOT_SET')
    expect(backendCodes()).toContain('OUTFIT_NOT_FOUND')
  })

  it('has an English message for every code the backend sends', () => {
    const missing = Array.from(backendCodes()).filter((code) => !(code in en.codes)).sort()
    expect(missing).toEqual([])
  })
})
