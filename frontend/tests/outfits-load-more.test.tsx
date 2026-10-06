import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, renderHook, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OutfitsPage from '@/app/dashboard/outfits/page'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/hooks/query-keys'
import { useBulkDeleteOutfits } from '@/lib/hooks/use-outfits'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
  setAccessToken: vi.fn(),
}))
vi.mock('@/components/outfits/outfit-card', () => ({
  OutfitCard: ({ outfit }: { outfit: { id: string } }) => <div>{outfit.id}</div>,
}))

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  client.setQueryData(['user-profile'], { timezone: 'UTC' })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

afterEach(() => {
  vi.mocked(api.get).mockReset()
})

describe('outfits load more', () => {
  it('keeps the first page and appends the second', async () => {
    vi.mocked(api.get).mockImplementation(async (_path, options) => {
      const params = (options as { params: Record<string, string> }).params
      const page = Number(params.page)
      if (params.is_lookbook) {
        return { outfits: [], total: 1, page: 1, page_size: 1, has_more: false }
      }
      return {
        outfits: [{ id: `outfit-page-${page}` }],
        total: 2,
        page,
        page_size: 1,
        has_more: page === 1,
      }
    })

    render(<OutfitsPage />, { wrapper })

    expect(await screen.findByText('outfit-page-1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'loadMore' }))

    expect(await screen.findByText('outfit-page-2')).toBeInTheDocument()
    expect(screen.getByText('outfit-page-1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'loadMore' })).not.toBeInTheDocument()
  })
})

describe('bulk outfit delete', () => {
  it('removes the deleted outfits from every loaded page of the infinite list', async () => {
    vi.mocked(api.post).mockResolvedValue({ deleted: 1 })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const key = queryKeys.outfits.infinite({}, 1)
    client.setQueryData(key, {
      pages: [
        { outfits: [{ id: 'a' }], total: 2, page: 1, page_size: 1, has_more: true },
        { outfits: [{ id: 'b' }], total: 2, page: 2, page_size: 1, has_more: false },
      ],
      pageParams: [1, 2],
    })
    const { result } = renderHook(useBulkDeleteOutfits, {
      wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
    })

    await act(() => result.current.mutateAsync({ outfit_ids: ['b'] }))

    const data = client.getQueryData<{ pages: { outfits: { id: string }[]; total: number }[] }>(key)
    expect(data?.pages.map((page) => page.outfits.map((outfit) => outfit.id))).toEqual([['a'], []])
    expect(data?.pages[0].total).toBe(1)
  })
})
