import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import { toast } from 'sonner'
import { ItemDetailDialog } from '@/components/item-detail-dialog'
import { api, ApiError } from '@/lib/api'
import { queryKeys } from '@/lib/hooks/query-keys'
import { useItem, useRemoveBackground } from '@/lib/hooks/use-items'
import type { Item, ItemListResponse } from '@/lib/types'

vi.unmock('next-intl')
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

function catalog(namespace: string) {
  return JSON.parse(readFileSync(resolve(__dirname, '..', 'messages', 'en', `${namespace}.json`), 'utf8'))
}
const wardrobe = catalog('wardrobe')
const errors = catalog('errors')
const itemDetail = wardrobe.itemDetail

const item = {
  id: 'i1',
  type: 'shirt',
  status: 'ready',
  processing_kind: null,
  tags: { colors: ['navy'], style: [], season: [] },
  images: [],
  image_url: 'https://example.test/i1.jpg?x=1',
  thumbnail_url: 'https://example.test/i1-thumb.jpg',
  wear_count: 0,
  wears_since_wash: 0,
  effective_wash_interval: 3,
} as unknown as Item

function makeClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  client.setQueryData(queryKeys.features, { background_removal: true, max_upload_size_mb: 20, ai_ui_enabled: true })
  return client
}

function wrapperFor(client: QueryClient) {
  const messages = Object.fromEntries(
    ['wardrobe', 'constants', 'common', 'errors'].map((ns) => [ns, catalog(ns)])
  )
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <NextIntlClientProvider locale="en" messages={messages} onError={() => {}}>
          {children}
        </NextIntlClientProvider>
      </QueryClientProvider>
    )
  }
}

function renderDialog(client: QueryClient, overrides: Partial<Item> = {}) {
  const Wrapper = wrapperFor(client)
  const dialog = (props: Partial<Item>) => (
    <Wrapper>
      <ItemDetailDialog item={{ ...item, ...props } as Item} open onOpenChange={() => {}} />
    </Wrapper>
  )
  const view = render(dialog(overrides))
  return { rerender: (next: Partial<Item>) => view.rerender(dialog(next)) }
}

const removeButton = () => screen.getByTitle(itemDetail.titles.removeBackground)

function invalidatedKeys(spy: MockInstance<QueryClient['invalidateQueries']>) {
  return spy.mock.calls.map(([filters]) => filters?.queryKey)
}

beforeEach(() => {
  vi.mocked(api.get).mockReset()
  vi.mocked(api.get).mockResolvedValue([])
  vi.mocked(api.post).mockReset()
  vi.mocked(api.post).mockResolvedValue({ status: 'queued', job_id: 'j1' })
  vi.mocked(toast.success).mockClear()
  vi.mocked(toast.error).mockClear()
})

describe('useRemoveBackground', () => {
  it('marks the item as having its background removed in the list and item caches', async () => {
    const client = makeClient()
    const listKey = queryKeys.items.list({}, 1, 20)
    client.setQueryData(listKey, {
      items: [item, { ...item, id: 'i2' }],
      total: 2,
      page: 1,
      page_size: 20,
      has_more: false,
    } as unknown as ItemListResponse)
    client.setQueryData<Item>(queryKeys.item('i1'), item)
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    const { result } = renderHook(() => useRemoveBackground(), { wrapper: wrapperFor(client) })
    await act(() => result.current.mutateAsync({ id: 'i1' }))

    const list = client.getQueryData<ItemListResponse>(listKey)!
    expect(list.items[0]).toMatchObject({ status: 'processing', processing_kind: 'background_removal' })
    expect(list.items[1]).toMatchObject({ status: 'ready' })
    expect(client.getQueryData<Item>(queryKeys.item('i1'))).toMatchObject({
      status: 'processing',
      processing_kind: 'background_removal',
    })
    expect(invalidatedKeys(invalidate)).toEqual([['items']])
  })
})

describe('useItem', () => {
  function intervalFor(status: Item['status']) {
    const client = makeClient()
    client.setQueryData<Item>(queryKeys.item('i1'), { ...item, status })
    renderHook(() => useItem('i1'), { wrapper: wrapperFor(client) })
    const query = client.getQueryCache().find({ queryKey: queryKeys.item('i1') })!
    const options = query.options as { refetchInterval?: (q: typeof query) => number | false }
    return options.refetchInterval?.(query)
  }

  it('polls while the item is processing so the dialog sees the job finish', () => {
    expect(intervalFor('processing')).toBe(5000)
  })

  it('does not poll an idle item', () => {
    expect(intervalFor('ready')).toBe(false)
    expect(intervalFor('error')).toBe(false)
  })
})

describe('remove background in the item dialog', () => {
  it('queues the removal and says so', async () => {
    renderDialog(makeClient())
    fireEvent.click(removeButton())

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(wardrobe.ai.removeBackgroundQueued))
    expect(api.post).toHaveBeenCalledWith('/items/i1/remove-background', { bg_color: '#FFFFFF' })
  })

  it('labels the photo overlay as background removal while the job runs', () => {
    renderDialog(makeClient(), { status: 'processing', processing_kind: 'background_removal' })
    expect(screen.getByText(wardrobe.ai.removingBackground)).toBeInTheDocument()
    expect(screen.queryByText(itemDetail.view.aiAnalyzing)).not.toBeInTheDocument()
  })

  it('keeps the analysis label for a tagging job', () => {
    renderDialog(makeClient(), { status: 'processing', processing_kind: null })
    expect(screen.getByText(itemDetail.view.aiAnalyzing)).toBeInTheDocument()
  })

  it('cannot be started while the item is processing', () => {
    renderDialog(makeClient(), { status: 'processing', processing_kind: null })
    expect(removeButton()).toBeDisabled()
  })

  it('shows the translated reason when the server refuses', async () => {
    vi.mocked(api.post).mockRejectedValue(
      new ApiError('Item is archived', 409, { detail: 'Item is archived', error_code: 'ITEM_ARCHIVED' })
    )
    renderDialog(makeClient())
    fireEvent.click(removeButton())

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(errors.ITEM_ARCHIVED))
  })

  it.each([
    ['finishes', { status: 'ready', processing_kind: null }, false],
    ['keeps a tagging failure', { status: 'error', processing_kind: null }, false],
    ['fails', { status: 'error', processing_kind: 'background_removal' }, true],
  ] as const)('refreshes the photo when the job %s', async (_name, end, toastsError) => {
    const client = makeClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const { rerender } = renderDialog(client)
    fireEvent.click(removeButton())
    await waitFor(() => expect(toast.success).toHaveBeenCalled())

    rerender({ status: 'processing', processing_kind: 'background_removal' })
    invalidate.mockClear()
    rerender(end as Partial<Item>)

    await waitFor(() =>
      expect(invalidatedKeys(invalidate)).toEqual(
        expect.arrayContaining([['item', 'i1'], ['outfits'], ['calendarOutfits']])
      )
    )
    expect(toast.error).toHaveBeenCalledTimes(toastsError ? 1 : 0)
    if (toastsError) expect(toast.error).toHaveBeenCalledWith(itemDetail.actions.backgroundRemoveError)
  })

  it('ignores a job it did not start', () => {
    const client = makeClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const { rerender } = renderDialog(client, { status: 'processing', processing_kind: 'background_removal' })

    rerender({ status: 'error', processing_kind: 'background_removal' })

    expect(invalidatedKeys(invalidate)).not.toContainEqual(['outfits'])
    expect(toast.error).not.toHaveBeenCalled()
  })
})
