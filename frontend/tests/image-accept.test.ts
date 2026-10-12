import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ACCEPTED_IMAGE_INPUT, ACCEPTED_IMAGE_TYPES } from '@/lib/image-types'
import { sourceFiles } from './source-files'

function backendExtensions(): string[] {
  const source = readFileSync(
    resolve(__dirname, '..', '..', 'backend', 'app', 'services', 'image_service.py'),
    'utf8',
  )
  const table = source.slice(source.indexOf('IMAGE_MIME_TYPES = {'), source.indexOf('}', source.indexOf('IMAGE_MIME_TYPES = {')))
  return Array.from(table.matchAll(/"(\.\w+)":/g), (m) => m[1])
}

describe('accepted image types', () => {
  it('match the extensions the backend accepts', () => {
    expect(Object.values(ACCEPTED_IMAGE_TYPES).flat().sort()).toEqual(backendExtensions().sort())
  })

  it('give native file inputs the same extension list', () => {
    expect(ACCEPTED_IMAGE_INPUT.split(',').sort()).toEqual(backendExtensions().sort())
  })

  it('are used by every file input instead of a wildcard', () => {
    const offenders = sourceFiles()
      .filter((f) => /accept=["']image\/\*["']/.test(f.text))
      .map((f) => f.path)
    expect(offenders).toEqual([])
  })
})
