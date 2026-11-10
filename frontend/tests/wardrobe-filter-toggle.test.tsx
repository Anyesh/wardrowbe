import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import WardrobePage from '@/app/dashboard/wardrobe/page'
import { api } from '@/lib/api'

const nav = vi.hoisted(() => ({ params: new URLSearchParams() }))

vi.unmock('next-intl')
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  usePathname: () => '/dashboard/wardrobe',
  useSearchParams: () => nav.params,
}))
vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
  setAccessToken: vi.fn(),
}))

function messages(namespace: string) {
  return JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', 'en', `${namespace}.json`), 'utf8'),
  )
}

function wrapper({ children }: { children: ReactNode }) {
  const all = Object.fromEntries(
    ['wardrobe', 'constants', 'common'].map((ns) => [ns, messages(ns)]),
  )
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  client.setQueryData(['user-profile'], { timezone: 'UTC' })
  return (
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="en" messages={all} onError={() => {}}>
        {children}
      </NextIntlClientProvider>
    </QueryClientProvider>
  )
}

function mockEmptyWardrobe() {
  vi.mocked(api.get).mockImplementation(async (path) =>
    path === '/items'
      ? { items: [], total: 0, page: 1, page_size: 20, has_more: false }
      : path === '/items/types'
        ? []
        : {}
  )
}

describe('wardrobe filter toggle', () => {
  it('names how many filters are active and whether the filter row is open', async () => {
    nav.params = new URLSearchParams('needsWash=true&favorite=true&type=shirt')
    mockEmptyWardrobe()

    render(<WardrobePage />, { wrapper })

    const toggle = await screen.findByRole('button', { name: 'Filters, 3 active' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })

  it('is named plainly when no filter is active', async () => {
    nav.params = new URLSearchParams()
    mockEmptyWardrobe()

    render(<WardrobePage />, { wrapper })

    expect(await screen.findByRole('button', { name: 'Filters' })).toBeInTheDocument()
  })
})
