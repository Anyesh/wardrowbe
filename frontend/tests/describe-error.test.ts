import { describe, expect, it } from 'vitest'
import en from '@/messages/en/errors.json'
import { ApiError, NetworkError } from '@/lib/api'
import { describeError, type ErrorTranslator } from '@/lib/errors'

const lookup = (key: string): unknown =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en)

const t = Object.assign(
  (key: string, values?: Record<string, string | number>) =>
    `${lookup(key) as string}${values ? ` ${JSON.stringify(values)}` : ''}`,
  { has: (key: string) => typeof lookup(key) === 'string' },
) as ErrorTranslator

describe('describeError', () => {
  it.each(['offline', 'unreachable', 'cancelled'] as const)('translates a %s network error', (kind) => {
    expect(describeError(new NetworkError(kind), t, 'fallback')).toBe(en.network[kind])
  })

  it('translates a top-level error_code with its params', () => {
    const error = new ApiError('Maximum 20 images per bulk upload', 400, {
      detail: 'Maximum 20 images per bulk upload',
      error_code: 'BULK_UPLOAD_LIMIT',
      error_params: { limit: 20 },
    })
    expect(describeError(error, t, 'fallback')).toBe(`${en.codes.BULK_UPLOAD_LIMIT} {"limit":20}`)
  })

  it('reads a code nested in detail', () => {
    const error = new ApiError('Outfit not found', 404, {
      detail: { message: 'Outfit not found', error_code: 'OUTFIT_NOT_FOUND' },
    })
    expect(describeError(error, t, 'fallback')).toBe(en.codes.OUTFIT_NOT_FOUND)
  })

  it.each([
    ['an unknown code', new ApiError('Nope', 400, { detail: 'Nope', error_code: 'SOMETHING_NEW' })],
    ['no code', new ApiError('User location not set', 400, { detail: 'User location not set' })],
    ['a plain Error', new Error('Unable to determine location from network')],
    ['a non-error', 'boom'],
  ])('falls back instead of showing English for %s', (_, error) => {
    expect(describeError(error, t, 'fallback')).toBe('fallback')
  })
})
