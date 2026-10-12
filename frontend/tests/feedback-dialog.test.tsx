import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FeedbackDialog } from '@/components/feedback-dialog'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/hooks/query-keys'
import { GRID_PAGE_SIZE } from '@/lib/pagination'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
  setAccessToken: vi.fn(),
}))
vi.mock('next/image', () => ({ default: () => null }))

const item = (id: string) => ({
  id,
  name: `Item ${id}`,
  type: 'shirt',
  image_path: `/${id}.jpg`,
  is_archived: false,
})

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.mocked(api.get).mockReset()
})

describe('FeedbackDialog wore-instead picker', () => {
  it('shows the cached first page after the search debounce settles', async () => {
    vi.mocked(api.get).mockResolvedValue({
      items: [item('b')],
      total: 1,
      page: 1,
      page_size: GRID_PAGE_SIZE,
      has_more: false,
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })
    client.setQueryData(queryKeys.items.list({ is_archived: false }, 1, GRID_PAGE_SIZE), {
      items: [item('a')],
      total: 1,
      page: 1,
      page_size: GRID_PAGE_SIZE,
      has_more: false,
    })

    render(
      <QueryClientProvider client={client}>
        <FeedbackDialog outfit={{ id: 'o1', items: [], feedback: null }} open onClose={() => {}} />
      </QueryClientProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: /noWoreSomethingElse/ }))
    await act(() => vi.advanceTimersByTimeAsync(500))

    expect(screen.getByText('Item a')).toBeInTheDocument()
    expect(screen.queryByText('noItemsInWardrobe')).not.toBeInTheDocument()
  })
})
