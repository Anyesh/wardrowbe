import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PairingsPage from '@/app/dashboard/pairings/page'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
  setAccessToken: vi.fn(),
}))
vi.mock('@/lib/hooks/use-items', () => ({ useItemTypes: () => ({ data: [] }) }))
vi.mock('@/components/pairing-card', () => ({
  PairingCard: ({ pairing }: { pairing: { id: string } }) => <div>{pairing.id}</div>,
}))

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

afterEach(() => {
  vi.mocked(api.get).mockReset()
})

describe('pairings load more', () => {
  it('keeps the first page and appends the second', async () => {
    vi.mocked(api.get).mockImplementation(async (_path, options) => {
      const page = Number((options as { params: { page: string } }).params.page)
      return {
        pairings: [{ id: `pairing-page-${page}` }],
        total: 2,
        page,
        page_size: 1,
        has_more: page === 1,
      }
    })

    render(<PairingsPage />, { wrapper })

    expect(await screen.findByText('pairing-page-1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'loadMore' }))

    expect(await screen.findByText('pairing-page-2')).toBeInTheDocument()
    expect(screen.getByText('pairing-page-1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'loadMore' })).not.toBeInTheDocument()
  })
})
