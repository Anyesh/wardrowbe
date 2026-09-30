import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { CLOTHING_SUBTYPES } from '@/lib/types'

const PROMPT_PATH = resolve(__dirname, '..', '..', 'backend', 'app', 'prompts', 'clothing_analysis.txt')

function parsePromptSubtypes(): Record<string, string[]> {
  const lines = readFileSync(PROMPT_PATH, 'utf8').split('\n')
  const start = lines.findIndex((line) => /^SUBTYPE\b.*Examples:/.test(line))
  if (start === -1) {
    throw new Error(`No "SUBTYPE ... Examples:" header found in ${PROMPT_PATH}`)
  }

  const parsed: Record<string, string[]> = {}
  for (const line of lines.slice(start + 1)) {
    const match = line.match(/^- (\S+) → (.+)$/)
    if (!match) break
    parsed[match[1]] = match[2].split(',').map((value) => value.trim())
  }
  return parsed
}

describe('CLOTHING_SUBTYPES', () => {
  it('matches the SUBTYPE examples in the vision prompt', () => {
    const fromPrompt = parsePromptSubtypes()

    expect(Object.keys(fromPrompt).length).toBeGreaterThan(0)
    expect(CLOTHING_SUBTYPES).toEqual(fromPrompt)
  })
})
