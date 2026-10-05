import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ItemDetailDialog } from '@/components/item-detail-dialog'
import type { Item } from '@/lib/types'

const { saveItem } = vi.hoisted(() => ({ saveItem: vi.fn() }))

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => <img src={src} alt={alt} />,
}))

vi.mock('@/lib/hooks/use-items', () => {
  const idleMutation = { isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }
  return {
    useUpdateItem: () => ({ ...idleMutation, mutateAsync: saveItem }),
    useDeleteItem: () => idleMutation,
    useReanalyzeItem: () => idleMutation,
    useRotateImage: () => idleMutation,
    useRemoveBackground: () => idleMutation,
    useRestoreOriginal: () => idleMutation,
    useReplaceItemImage: () => idleMutation,
    useLogWash: () => idleMutation,
    useWashHistory: () => ({ data: undefined }),
    useItemWearStats: () => ({ data: undefined }),
    useItemWearHistory: () => ({ data: undefined }),
    useAddItemImage: () => idleMutation,
    useDeleteItemImage: () => idleMutation,
    useSetPrimaryImage: () => idleMutation,
  }
})

vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useClothingTypes: () => [{ value: 'shirt', label: 'Shirt' }],
  useClothingColors: () => [],
  useFormalityLabel: () => (value: string) => value,
  useMaterialLabel: () => (value: string) => value,
  useSubtypeLabel: () => (value: string) => value,
}))

vi.mock('@/lib/hooks/use-features', () => ({ useFeatures: () => ({ data: {} }) }))
vi.mock('@/components/color-eyedropper', () => ({ ColorEyedropper: () => null }))
vi.mock('@/components/generate-pairings-dialog', () => ({ GeneratePairingsDialog: () => null }))

function item(overrides: Partial<Item> = {}): Item {
  return {
    id: 'item-1',
    user_id: 'user-1',
    type: 'shirt',
    name: 'Oxford shirt',
    favorite: false,
    image_path: '/shirt.jpg',
    image_url: '/shirt.jpg',
    tags: { colors: [], style: [], season: [] },
    colors: [],
    status: 'ready',
    ai_processed: false,
    tagging_status: 'tagged',
    wear_count: 0,
    suggestion_count: 0,
    acceptance_count: 0,
    wears_since_wash: 0,
    needs_wash: false,
    effective_wash_interval: 3,
    additional_images: [],
    is_archived: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function openEditor(value: Item) {
  render(<ItemDetailDialog item={value} open onOpenChange={vi.fn()} />)
  fireEvent.click(screen.getByTitle('actions.editItem'))
}

describe('garment metadata editor', () => {
  beforeEach(() => {
    saveItem.mockReset().mockResolvedValue({})
  })

  it('prefills and saves size, store, and care instructions', async () => {
    openEditor(item({ size: 'M', purchase_store: 'Example Store', care_instructions: 'Wash cold' }))

    expect(screen.getByLabelText('size')).toHaveValue('M')
    expect(screen.getByLabelText('purchaseStore')).toHaveValue('Example Store')
    expect(screen.getByLabelText('careInstructions')).toHaveValue('Wash cold')

    fireEvent.change(screen.getByLabelText('size'), { target: { value: 'L' } })
    fireEvent.change(screen.getByLabelText('purchaseStore'), { target: { value: 'Another Store' } })
    fireEvent.change(screen.getByLabelText('careInstructions'), { target: { value: 'Lay flat to dry' } })
    fireEvent.click(screen.getByRole('button', { name: 'save' }))

    await waitFor(() => expect(saveItem).toHaveBeenCalledWith({
      id: 'item-1',
      data: expect.objectContaining({
        size: 'L',
        purchase_store: 'Another Store',
        care_instructions: 'Lay flat to dry',
      }),
    }))
  })

  it('sends null when the three fields are cleared', async () => {
    openEditor(item({ size: 'M', purchase_store: 'Example Store', care_instructions: 'Wash cold' }))

    for (const label of ['size', 'purchaseStore', 'careInstructions']) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: '' } })
    }
    fireEvent.click(screen.getByRole('button', { name: 'save' }))

    await waitFor(() => expect(saveItem).toHaveBeenCalledWith({
      id: 'item-1',
      data: expect.objectContaining({
        size: null,
        purchase_store: null,
        care_instructions: null,
      }),
    }))
  })
})
