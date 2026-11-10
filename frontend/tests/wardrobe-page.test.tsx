import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import WardrobePage from '@/app/dashboard/wardrobe/page'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock('@/lib/hooks/use-items', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/hooks/use-items')>()
  const query = { data: undefined, isLoading: false, error: null }
  const mutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }
  return {
    ...actual,
    useItems: () => ({ ...query, data: { items: [], total: 0 } }),
    useItem: () => query,
    useItemTypes: () => query,
    useTaggingProgress: () => query,
    useReanalyzeItem: () => mutation,
    useCancelAnalysis: () => mutation,
    useBulkDeleteItems: () => mutation,
    useBulkReanalyzeItems: () => mutation,
    useBulkCancelAnalysis: () => mutation,
    useBulkRotateItems: () => mutation,
    useBulkRemoveBackgroundItems: () => mutation,
    useRemoveBackground: () => mutation,
  }
})

vi.mock('@/lib/hooks/use-user', () => ({ useUserTimezone: () => 'UTC' }))

vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useClothingTypes: () => [],
  useClothingColors: () => [],
  useSubtypeLabel: () => (value: string) => value,
  useTypeLabel: () => (value: string) => value,
}))

vi.mock('@/components/add-item-dialog', () => ({ AddItemDialog: () => null }))
vi.mock('@/components/analysis-queue-panel', () => ({ AnalysisQueuePanel: () => null }))
vi.mock('@/components/item-detail-dialog', () => ({ ItemDetailDialog: () => null }))
vi.mock('@/components/bulk-action-toolbar', () => ({ BulkActionToolbar: () => null }))

describe('WardrobePage add buttons', () => {
  it('names both the phone and desktop add buttons', () => {
    render(<WardrobePage />)

    expect(screen.getAllByRole('button', { name: 'actions.addItem' })).toHaveLength(2)
  })
})
