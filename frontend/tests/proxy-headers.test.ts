import { describe, it, expect, afterEach } from 'vitest'
import { decodeProxyHeader, proxySecretMatches } from '@/lib/proxy-headers'

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

  it.each([
    ['voilà', 'voilÃ'],
    ['Å', 'Ã'],
  ])('tells apart ids that differ only in a trailing UTF-8 byte: %s', (value, other) => {
    expect(decodeProxyHeader(asNodeReadsIt(value))).not.toBe(decodeProxyHeader(asNodeReadsIt(other)))
  })

  it('trims spaces and tabs around the decoded value', () => {
    expect(decodeProxyHeader('  carol\t')).toBe('carol')
    expect(decodeProxyHeader(asNodeReadsIt(' 山田\t'))).toBe('山田')
  })
})

describe('proxySecretMatches', () => {
  const originalEnv = { ...process.env }
  const SECRET = 'proxy-shared-secret-that-is-long-enough'

  afterEach(() => {
    process.env = { ...originalEnv }
  })

  it.each([
    ['the configured secret', SECRET, SECRET, true],
    ['a secret differing in its last character', `${SECRET.slice(0, -1)}X`, SECRET, false],
    ['a prefix of the secret', SECRET.slice(0, 10), SECRET, false],
    ['the secret with more after it', `${SECRET}x`, SECRET, false],
    ['no header', null, SECRET, false],
    ['an empty header when no secret is configured', '', undefined, false],
    ['any header when no secret is configured', SECRET, undefined, false],
  ])('compares %s', (_label, presented, configured, expected) => {
    if (configured === undefined) delete process.env.FORWARD_AUTH_SECRET
    else process.env.FORWARD_AUTH_SECRET = configured

    expect(proxySecretMatches(presented)).toBe(expected)
  })
})
