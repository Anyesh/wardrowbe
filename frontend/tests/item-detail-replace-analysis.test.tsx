import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ItemDetailDialog } from '@/components/item-detail-dialog'
import { api } from '@/lib/api'
import type { Item } from '@/lib/types'
import { toast } from 'sonner'

vi.unmock('next-intl')
vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

function catalog(namespace: string) {
  return JSON.parse(readFileSync(resolve(__dirname, '..', 'messages', 'en', `${namespace}.json`), 'utf8'))
}
const wardrobe = catalog('wardrobe')
const itemDetail = wardrobe.itemDetail

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const all = Object.fromEntries(['wardrobe', 'constants', 'common'].map((ns) => [ns, catalog(ns)]))
  return (
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="en" messages={all} onError={() => {}}>
        {children}
      </NextIntlClientProvider>
    </QueryClientProvider>
  )
}

const item = {
  id: 'i1',
  type: 'shirt',
  status: 'ready',
  tags: { colors: ['navy'], style: [], season: [] },
  images: [],
  image_url: 'https://example.test/i1.jpg?x=1',
  thumbnail_url: 'https://example.test/i1-thumb.jpg',
  wear_count: 0,
  wears_since_wash: 0,
  effective_wash_interval: 3,
} as unknown as Item

function renderDialog(overrides: Partial<Item> = {}) {
  render(<ItemDetailDialog item={{ ...item, ...overrides } as Item} open onOpenChange={() => {}} />, {
    wrapper: Wrapper,
  })
}

const replaceButton = () => screen.getByTitle(itemDetail.titles.reanalyzeAndReplace)

describe('re-analyse and replace', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(api.post).mockReset()
    vi.mocked(api.post).mockResolvedValue({ status: 'queued', job_id: 'j1' })
    vi.mocked(toast.info).mockClear()
  })

  it('asks before replacing and explains what is kept', () => {
    renderDialog()
    fireEvent.click(replaceButton())

    expect(screen.getByText(itemDetail.replaceAnalysis.title)).toBeInTheDocument()
    expect(screen.getByText(itemDetail.replaceAnalysis.description)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('does nothing when cancelled', async () => {
    renderDialog()
    fireEvent.click(replaceButton())
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByText(itemDetail.replaceAnalysis.title)).not.toBeInTheDocument())
    expect(api.post).not.toHaveBeenCalled()
  })

  it('queues a replacing analysis when confirmed', async () => {
    renderDialog()
    fireEvent.click(replaceButton())
    fireEvent.click(screen.getByRole('button', { name: itemDetail.replaceAnalysis.confirm }))

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    expect(api.post).toHaveBeenCalledWith('/items/i1/analyze?replace=true')
  })

  it('leaves the ordinary re-analyse button as it was', async () => {
    renderDialog()
    fireEvent.click(screen.getByTitle(itemDetail.titles.reanalyzeWithAI))

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    expect(api.post).toHaveBeenCalledWith('/items/i1/analyze')
  })

  it('tells the user when the item is cooling down after a failure', async () => {
    vi.mocked(api.post).mockResolvedValue({ status: 'cooldown', retry_after_seconds: 42 })
    renderDialog()
    fireEvent.click(replaceButton())
    fireEvent.click(screen.getByRole('button', { name: itemDetail.replaceAnalysis.confirm }))

    await waitFor(() => expect(toast.info).toHaveBeenCalledTimes(1))
  })

  it('is disabled while the item is being analysed', () => {
    renderDialog({ status: 'processing' } as Partial<Item>)
    expect(replaceButton()).toBeDisabled()
  })
})
