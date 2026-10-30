import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import WardrobePage from '@/app/dashboard/wardrobe/page'
import { api } from '@/lib/api'
import { useItems } from '@/lib/hooks/use-items'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  usePathname: () => '/dashboard/wardrobe',
  useSearchParams: () => new URLSearchParams('needsWash=true&favorite=true&type=shirt&search=blue'),
}))
vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
  setAccessToken: vi.fn(),
}))

const PAGE_ONLY_PARAMS = new Set(['page', 'page_size', 'sort_by', 'sort_order'])

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  client.setQueryData(['user-profile'], { timezone: 'UTC' })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

afterEach(() => {
  vi.mocked(api.get).mockReset()
  vi.mocked(api.post).mockReset()
})

describe('wardrobe select-all', () => {
  it('sends the list query filters with the bulk request', async () => {
    let listParams: Record<string, string> = {}
    vi.mocked(api.get).mockImplementation(async (path, options) => {
      if (path === '/items') {
        listParams = (options as { params: Record<string, string> }).params
        return {
          items: [{ id: 'item-1', name: 'Blue shirt', type: 'shirt', status: 'ready', tags: {}, colors: [] }],
          total: 30,
          page: 1,
          page_size: 1,
          has_more: true,
        }
      }
      return path === '/items/types' ? [] : {}
    })
    vi.mocked(api.post).mockResolvedValue({ queued: 29, failed: 0, has_more: false })

    render(<WardrobePage />, { wrapper })

    await screen.findAllByText('Blue shirt')
    fireEvent.click(await screen.findByText('selectAll'))
    fireEvent.click(await screen.findByText('bulkActions.selectAllMatching'))
    fireEvent.click(screen.getByRole('button', { name: 'bulkActions.rotateCw' }))

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    const [path, body] = vi.mocked(api.post).mock.calls[0] as [
      string,
      { select_all: boolean; filters: Record<string, unknown> },
    ]
    expect(path).toBe('/items/bulk/rotate')
    expect(body.select_all).toBe(true)

    const listFilters = Object.fromEntries(
      Object.entries(listParams).filter(([key]) => !PAGE_ONLY_PARAMS.has(key))
    )
    const bulkFilters = Object.fromEntries(
      Object.entries(body.filters)
        .filter(([, value]) => value !== undefined)
        .map(([key, value]) => [key, String(value)])
    )
    expect(bulkFilters).toEqual(listFilters)
    expect(Object.keys(listFilters).sort()).toEqual(
      ['favorite', 'is_archived', 'needs_wash', 'search', 'type'].sort()
    )
  })
})

describe('item list query', () => {
  it('sends every filter the bulk request would carry', async () => {
    vi.mocked(api.get).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, has_more: false })

    renderHook(
      () =>
        useItems({
          type: 'shirt',
          subtype: 'polo',
          colors: ['red', 'navy'],
          status: 'ready',
          favorite: false,
          needs_wash: true,
          is_archived: false,
          search: '',
        }),
      { wrapper }
    )

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/items', expect.anything()))
    const [, options] = vi.mocked(api.get).mock.calls.find(([path]) => path === '/items')!
    expect((options as { params: Record<string, string> }).params).toEqual({
      page: '1',
      page_size: '20',
      type: 'shirt',
      subtype: 'polo',
      colors: 'red,navy',
      status: 'ready',
      favorite: 'false',
      needs_wash: 'true',
      is_archived: 'false',
    })
  })
})
