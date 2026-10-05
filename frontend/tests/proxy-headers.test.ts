import { describe, it, expect } from 'vitest'
import { decodeProxyHeader } from '@/lib/proxy-headers'

function asNodeReadsIt(utf8: string) {
  return String.fromCharCode(...Array.from(new TextEncoder().encode(utf8)))
}

describe('decodeProxyHeader', () => {
  it.each(['José Müller', '山田太郎', 'Zoë 🧥'])('restores the UTF-8 the proxy sent for %s', (value) => {
    expect(decodeProxyHeader(asNodeReadsIt(value))).toBe(value)
  })

  it('leaves ASCII untouched', () => {
    expect(decodeProxyHeader('alice@example.com')).toBe('alice@example.com')
  })

  it('keeps a value whose bytes are not valid UTF-8, as the backend does', () => {
    expect(decodeProxyHeader('café')).toBe('café')
  })

  it('keeps a value that was never Latin-1 decoded', () => {
    expect(decodeProxyHeader('山田')).toBe('山田')
  })

  // These cases match test_remote_user_is_decoded_before_trimming in the backend suite, so a
  // session's sub and the backend's external_id come from the same bytes.
  it.each([
    ['voilà', 'voilà'],
    ['voilÃ', 'voilÃ'],
    ['bob\u00a0', 'bob\u00a0'],
  ])('keeps UTF-8 characters whose last byte Latin-1 calls whitespace: %s', (value, expected) => {
    expect(decodeProxyHeader(asNodeReadsIt(value))).toBe(expected)
  })

  it('tells apart ids that differ only in a trailing UTF-8 byte', () => {
    expect(decodeProxyHeader(asNodeReadsIt('voilà'))).not.toBe(decodeProxyHeader(asNodeReadsIt('voilÃ')))
  })

  it('trims spaces and tabs around the decoded value', () => {
    expect(decodeProxyHeader('  carol\t')).toBe('carol')
    expect(decodeProxyHeader(asNodeReadsIt(' 山田\t'))).toBe('山田')
  })
})
