import { describe, it, expect } from 'vitest'
import { ApiError, NetworkError } from '@/lib/api'
import { describeError, type ErrorTranslator } from '@/lib/errors'

const catalog: Record<string, string> = {
  OUTFIT_NOT_FOUND: 'Outfit nicht gefunden',
  BULK_ACTION_LIMIT_EXCEEDED: 'Höchstens {limit} Teile',
  NETWORK_OFFLINE: 'Du bist offline',
  NETWORK_CONNECT_FAILED: 'Server nicht erreichbar',
  BROKEN_FORMAT: 'unused',
}

const t = Object.assign(
  (key: string, values?: Record<string, string | number>) => {
    if (key === 'BROKEN_FORMAT') return `errors.${key}`
    return catalog[key].replace(/\{(\w+)\}/g, (_, name) => String(values?.[name]))
  },
  { has: (key: string) => key in catalog }
) as ErrorTranslator

const coded = (code: string | null, params?: Record<string, unknown>) =>
  new ApiError('Outfit not found', 404, { detail: 'Outfit not found', error_code: code, params })

describe('describeError', () => {
  it('translates a known code', () => {
    expect(describeError(coded('OUTFIT_NOT_FOUND'), t, 'fallback')).toBe('Outfit nicht gefunden')
  })

  it('fills params into the message', () => {
    expect(describeError(coded('BULK_ACTION_LIMIT_EXCEEDED', { limit: 100 }), t, 'fallback')).toBe(
      'Höchstens 100 Teile'
    )
  })

  it.each([
    ['an unknown code', coded('SOMETHING_NEW')],
    ['no code', coded(null)],
    ['a message that fails to format', coded('BROKEN_FORMAT')],
    ['a plain Error', new Error('Outfit not found')],
    ['a string', 'Outfit not found'],
  ])('falls back on %s and never shows the English text', (_, error) => {
    expect(describeError(error, t, 'fallback')).toBe('fallback')
  })

  it.each([
    ['offline', 'Du bist offline'],
    ['unreachable', 'Server nicht erreichbar'],
  ] as const)('translates a %s network error', (kind, text) => {
    expect(describeError(new NetworkError(kind), t, 'fallback')).toBe(text)
  })
})

describe('ApiError fields', () => {
  it('reads code and params from the top level and drops non-scalar params', () => {
    const error = coded('BULK_ACTION_LIMIT_EXCEEDED', { limit: 100, nested: { a: 1 }, name: 'x' })

    expect(error.code).toBe('BULK_ACTION_LIMIT_EXCEEDED')
    expect(error.params).toEqual({ limit: 100, name: 'x' })
  })
})
