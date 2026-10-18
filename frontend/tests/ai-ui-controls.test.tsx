import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OutfitsPage from '@/app/dashboard/outfits/page'
import { AddItemDialog } from '@/components/add-item-dialog'
import { ItemDetailDialog } from '@/components/item-detail-dialog'
import { DetailsPanel } from '@/components/studio/details-panel'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/hooks/query-keys'
import type { StudioItem } from '@/lib/studio/editor-state'
import type { Item } from '@/lib/types'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
  getErrorMessage: (error: unknown) => String(error),
}))
vi.mock('@/components/outfits/outfit-card', () => ({ OutfitCard: () => null }))

const item = {
  id: 'i1',
  type: 'shirt',
  status: 'ready',
  tags: { colors: ['navy'] },
  images: [],
  image_url: 'https://example.test/i1.jpg',
  thumbnail_url: 'https://example.test/i1-thumb.jpg',
  wear_count: 0,
  wears_since_wash: 0,
  effective_wash_interval: 3,
} as unknown as Item

const studioItem = { id: 'i1', type: 'shirt' } as unknown as StudioItem

function renderWithAiUi(ui: ReactElement, aiUiEnabled: boolean) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  client.setQueryData(queryKeys.features, {
    background_removal: false,
    max_upload_size_mb: 20,
    ai_ui_enabled: aiUiEnabled,
  })
  client.setQueryData(['user-profile'], { timezone: 'UTC' })
  render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.mocked(api.get).mockImplementation(async (path: string) =>
    path.startsWith('/outfits')
      ? { outfits: [], total: 0, page: 1, page_size: 20, has_more: false }
      : []
  )
})

describe.each([true, false])('AI controls with ai_ui_enabled=%s', (aiUiEnabled) => {
  const expectShown = (element: HTMLElement | null) =>
    aiUiEnabled ? expect(element).toBeInTheDocument() : expect(element).not.toBeInTheDocument()

  it('item detail dialog suggest, pairings and re-analyze buttons follow the switch', () => {
    renderWithAiUi(<ItemDetailDialog item={item} open onOpenChange={() => {}} />, aiUiEnabled)

    expectShown(screen.queryByTitle('titles.suggestOutfit'))
    expectShown(screen.queryByTitle('titles.findMatchingOutfits'))
    expectShown(screen.queryByTitle('titles.reanalyzeWithAI'))
    expect(screen.getByRole('button', { name: 'actions.logWear' })).toBeInTheDocument()
  })

  it('add item type picker offers AI detection only when the switch is on', () => {
    renderWithAiUi(<AddItemDialog open onOpenChange={() => {}} />, aiUiEnabled)

    expectShown(screen.queryByText('letAiDetect'))
    expect(screen.getAllByText('selectPlaceholder')).toHaveLength(aiUiEnabled ? 1 : 2)
  })

  it('outfit builder AI button follows the switch', () => {
    renderWithAiUi(
      <DetailsPanel
        items={[studioItem]}
        name=""
        occasion="casual"
        onNameChange={() => {}}
        onOccasionChange={() => {}}
        onAiMerge={() => {}}
      />,
      aiUiEnabled
    )

    expectShown(screen.queryByRole('button', { name: 'letAiFinish' }))
  })

  it('outfits page pairings filter follows the switch', async () => {
    renderWithAiUi(<OutfitsPage />, aiUiEnabled)

    expect(await screen.findByRole('button', { name: 'filters.worn' })).toBeInTheDocument()
    expectShown(screen.queryByRole('button', { name: 'filters.pairings' }))
  })
})
