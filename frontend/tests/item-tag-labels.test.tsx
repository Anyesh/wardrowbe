import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ItemDetailDialog } from '@/components/item-detail-dialog'
import type { Item } from '@/lib/types'

vi.unmock('next-intl')
vi.mock('@/lib/api', () => ({
  api: { get: vi.fn().mockResolvedValue([]), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
}))

function messages(locale: string, namespace: string) {
  return JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', locale, `${namespace}.json`), 'utf8'),
  )
}

function wrapperFor(locale: string) {
  const all = Object.fromEntries(
    ['wardrobe', 'constants', 'common'].map((ns) => [ns, messages(locale, ns)]),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <NextIntlClientProvider locale={locale} messages={all} onError={() => {}}>
          {children}
        </NextIntlClientProvider>
      </QueryClientProvider>
    )
  }
}

// The tagger only accepts values from these sets, so each needs a label in constants.
function backendTagValues(name: string): string[] {
  const source = readFileSync(
    resolve(__dirname, '..', '..', 'backend', 'app', 'services', 'ai_service.py'),
    'utf8',
  )
  const start = source.indexOf(`${name} = {`)
  const block = source.slice(start, source.indexOf('}', start))
  return Array.from(block.matchAll(/"([^"]+)"/g), (m) => m[1])
}

describe('item tag labels', () => {
  it.each([
    ['VALID_PATTERNS', 'patterns'],
    ['VALID_FIT', 'fits'],
    ['VALID_STYLES', 'styles'],
    ['VALID_SEASONS', 'seasons'],
  ])('has a constants label for every %s value', (backendSet, namespace) => {
    const values = backendTagValues(backendSet)
    expect(values.length).toBeGreaterThan(3)
    const labels = messages('en', 'constants')[namespace] ?? {}
    for (const value of values) expect(Object.keys(labels), value).toContain(value)
  })

  it('shows the AI tags in the user language', () => {
    const item = {
      id: 'i1',
      type: 'shirt',
      status: 'ready',
      tags: {
        colors: ['navy'],
        pattern: 'striped',
        style: ['preppy'],
        season: ['all-season'],
        fit: 'slim',
      },
      images: [],
      image_url: 'https://example.test/i1.jpg',
      thumbnail_url: 'https://example.test/i1-thumb.jpg',
    } as unknown as Item
    render(<ItemDetailDialog item={item} open onOpenChange={() => {}} />, {
      wrapper: wrapperFor('de'),
    })

    const constants = messages('de', 'constants')
    for (const label of [
      constants.colors.navy,
      constants.patterns.striped,
      constants.styles.preppy,
      constants.seasons['all-season'],
    ])
      expect(screen.getByText(label)).toBeInTheDocument()
    for (const raw of ['navy', 'striped', 'preppy', 'all-season'])
      expect(screen.queryByText(raw)).not.toBeInTheDocument()
  })
})
