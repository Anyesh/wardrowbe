import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ItemDetailDialog } from '@/components/item-detail-dialog'
import type { Item } from '@/lib/types'
import { api } from '@/lib/api'
import { toast } from 'sonner'

vi.unmock('next-intl')
vi.mock('@/lib/api', () => ({
  api: { get: vi.fn().mockResolvedValue([]), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

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
  wear_count: 0,
  wears_since_wash: 0,
  effective_wash_interval: 3,
} as unknown as Item

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

describe('log wear', () => {
  it('logs one wear, toasts and refetches the wear history', async () => {
    vi.mocked(api.get).mockClear()
    let finish: (value: unknown) => void = () => {}
    vi.mocked(api.post).mockReturnValueOnce(new Promise((resolve) => (finish = resolve)))
    render(<ItemDetailDialog item={item} open onOpenChange={() => {}} />, {
      wrapper: wrapperFor('en'),
    })
    const historyFetches = () =>
      vi.mocked(api.get).mock.calls.filter(([path]) => path.startsWith('/items/i1/history')).length
    await waitFor(() => expect(historyFetches()).toBe(1))

    const button = screen.getByRole('button', { name: 'Log wear' })
    fireEvent.click(button)
    await waitFor(() => expect(button).toBeDisabled())
    fireEvent.click(button)
    await act(async () => finish(item))

    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith('/items/i1/wear', { worn_at: undefined, occasion: undefined })
    expect(toast.success).toHaveBeenCalledWith(messages('en', 'wardrobe').itemDetail.actions.wearLogged)
    await waitFor(() => expect(historyFetches()).toBe(2))
  })
})
