// @vitest-environment node
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import en from '@/messages/en/errors.json'

const BACKEND_APP = resolve(__dirname, '..', '..', 'backend', 'app')

// Matches the ways the backend names a code: a detail dict, CodedHTTPException's code argument,
// and the first string argument of an exception that carries a code to an endpoint.
const CODE_PATTERNS = [
  /"error_code":\s*"([A-Z][A-Z0-9_]*)"/g,
  /CodedHTTPException\(\s*[^,()]+,\s*(?:error_code=)?"([A-Z][A-Z0-9_]*)"/g,
  /\w+Error\([^()]*?"([A-Z][A-Z0-9_]*)"/g,
  /error_code(?::\s*str)?\s*=\s*"([A-Z][A-Z0-9_]*)"/g,
]
// A CodedHTTPException whose code is not a literal must take it from an exception that the
// patterns above already cover.
const PASSTHROUGH = /CodedHTTPException\(\s*[^,()]+,\s*(?:error_code=)?e\.error_code\b/

function pythonFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return pythonFiles(full)
    return entry.endsWith('.py') ? [full] : []
  })
}

function unmatchedCalls(): string[] {
  const unmatched: string[] = []
  for (const file of pythonFiles(BACKEND_APP)) {
    const source = readFileSync(file, 'utf8')
    for (const match of Array.from(source.matchAll(/CodedHTTPException\([\s\S]{0,200}/g))) {
      const call = match[0]
      if (call.startsWith('CodedHTTPException(HTTPException)')) continue
      if (!CODE_PATTERNS[1].test(call) && !PASSTHROUGH.test(call)) unmatched.push(`${file}: ${call.slice(0, 80)}`)
      CODE_PATTERNS[1].lastIndex = 0
    }
  }
  return unmatched
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

  it('can read the code of every CodedHTTPException raised', () => {
    expect(unmatchedCalls()).toEqual([])
  })

  it('has an English message for every code the backend sends', () => {
    const missing = Array.from(backendCodes()).filter((code) => !(code in en.codes)).sort()
    expect(missing).toEqual([])
  })
})
