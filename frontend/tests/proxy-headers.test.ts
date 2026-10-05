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
})
