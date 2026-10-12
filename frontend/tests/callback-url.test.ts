import { describe, expect, it } from 'vitest'
import { safeCallbackUrl } from '@/lib/callback-url'

const ORIGIN = 'https://wardrobe.example'

describe('safeCallbackUrl', () => {
  it.each([
    ['/dashboard/outfits', '/dashboard/outfits'],
    ['/dashboard/outfits?page=2#top', '/dashboard/outfits?page=2#top'],
    [`${ORIGIN}/dashboard/wardrobe?x=1`, '/dashboard/wardrobe?x=1'],
    ['dashboard/history', '/dashboard/history'],
  ])('keeps the same-origin path %s', (value, expected) => {
    expect(safeCallbackUrl(value, ORIGIN)).toBe(expected)
  })

  it.each([
    [null],
    [''],
    ['//evil.example'],
    ['//evil.example/dashboard'],
    ['/\\evil.example'],
    ['\\\\evil.example'],
    ['/\t/evil.example'],
    ['/\n/evil.example'],
    ['\t//evil.example'],
    ['/%5Cevil.example'],
    ['/%5c%5cevil.example'],
    ['/%2F/evil.example'],
    ['/.//evil.example'],
    [`${ORIGIN}//evil.example`],
    ['https://evil.example/dashboard'],
    ['http://wardrobe.example/dashboard'],
    ['https://wardrobe.example.evil.example/dashboard'],
    ['javascript:alert(1)'],
    [' javascript:alert(1)'],
    ['data:text/html,<script>alert(1)</script>'],
    ['/%E0%A4%A'],
  ])('falls back to /dashboard for %j', (value) => {
    expect(safeCallbackUrl(value, ORIGIN)).toBe('/dashboard')
  })
})
