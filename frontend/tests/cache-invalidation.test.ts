import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import {
  useAddItemImage,
  useDeleteItemImage,
  useLogWash,
  useLogWear,
  useRemoveBackground,
  useReplaceItemImage,
  useRestoreOriginal,
  useRotateImage,
  useSetPrimaryImage,
  useUpdateItem,
} from '@/lib/hooks/use-items'
import {
  useAcceptOutfit,
  useBulkDeleteOutfits,
  useDeleteOutfit,
  useRejectOutfit,
  useSubmitFeedback,
} from '@/lib/hooks/use-outfits'
import { useCreateStudioOutfit, useCreateWoreInstead, useWearToday } from '@/lib/hooks/use-studio'

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}))

async function invalidatedKeys<V>(
  useHook: () => { mutateAsync: (vars: V) => Promise<unknown> },
  vars: V,
) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  const spy = vi.spyOn(queryClient, 'invalidateQueries')
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  const { result } = renderHook(useHook, { wrapper })
  await act(() => result.current.mutateAsync(vars))
  return spy.mock.calls.map(([filters]) => filters?.queryKey)
}

const ITEM_ONLY = [['items'], ['item', 'i1']]
const ITEM_AND_OUTFITS = [['items'], ['item', 'i1'], ['outfits'], ['calendarOutfits']]
const OUTFIT_LISTS = [['outfits'], ['calendarOutfits'], ['pendingOutfits'], ['analytics']]
const ITEM_WEAR = [['items'], ['item', 'i1'], ['wear-stats', 'i1'], ['wear-history', 'i1']]
const EVERY_ITEM_WEAR = [['items'], ['item'], ['wear-stats'], ['wear-history']]
const OUTFIT_AND_LISTS = [
  ['outfits'],
  ['outfit', 'o1'],
  ['calendarOutfits'],
  ['pendingOutfits'],
  ['analytics'],
]

describe('mutation cache invalidation', () => {
  const file = new File(['x'], 'x.jpg', { type: 'image/jpeg' })

  beforeEach(() => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({}) } as Response)
  })

  it.each([
    ['useUpdateItem', () => invalidatedKeys(useUpdateItem, { id: 'i1', data: {} }), ITEM_ONLY],
    ['useLogWear', () => invalidatedKeys(useLogWear, { id: 'i1' }), ITEM_WEAR],
    ['useAddItemImage', () => invalidatedKeys(useAddItemImage, { itemId: 'i1', file }), ITEM_ONLY],
    [
      'useDeleteItemImage',
      () => invalidatedKeys(useDeleteItemImage, { itemId: 'i1', imageId: 'm1' }),
      ITEM_ONLY,
    ],
    [
      'useSetPrimaryImage',
      () => invalidatedKeys(useSetPrimaryImage, { itemId: 'i1', imageId: 'm1' }),
      ITEM_AND_OUTFITS,
    ],
    [
      'useLogWash',
      () => invalidatedKeys(useLogWash, { id: 'i1' }),
      [['items'], ['item', 'i1'], ['wash-history', 'i1']],
    ],
    [
      'useRemoveBackground',
      () => invalidatedKeys(useRemoveBackground, { id: 'i1' }),
      ITEM_AND_OUTFITS,
    ],
    ['useRestoreOriginal', () => invalidatedKeys(useRestoreOriginal, 'i1'), ITEM_AND_OUTFITS],
    [
      'useReplaceItemImage',
      () => invalidatedKeys(useReplaceItemImage, { itemId: 'i1', file }),
      ITEM_AND_OUTFITS,
    ],
    [
      'useRotateImage',
      () => invalidatedKeys(useRotateImage, { id: 'i1', direction: 'cw' as const }),
      ITEM_AND_OUTFITS,
    ],
    ['useAcceptOutfit', () => invalidatedKeys(useAcceptOutfit, 'o1'), OUTFIT_AND_LISTS],
    ['useRejectOutfit', () => invalidatedKeys(useRejectOutfit, 'o1'), OUTFIT_AND_LISTS],
    [
      'useSubmitFeedback',
      () => invalidatedKeys(useSubmitFeedback, { outfitId: 'o1', feedback: {} }),
      OUTFIT_AND_LISTS,
    ],
    [
      'useSubmitFeedback (worn)',
      () => invalidatedKeys(useSubmitFeedback, { outfitId: 'o1', feedback: { worn: true } }),
      [...OUTFIT_AND_LISTS, ...EVERY_ITEM_WEAR],
    ],
    [
      'useCreateStudioOutfit',
      () => invalidatedKeys(useCreateStudioOutfit, { items: ['i1'], occasion: 'casual' }),
      [['outfits'], ['analytics'], ['learning']],
    ],
    [
      'useCreateStudioOutfit (worn)',
      () =>
        invalidatedKeys(useCreateStudioOutfit, {
          items: ['i1'],
          occasion: 'casual',
          mark_worn: true,
        }),
      [['outfits'], ['analytics'], ['learning'], ...EVERY_ITEM_WEAR],
    ],
    [
      'useCreateWoreInstead',
      () => invalidatedKeys(() => useCreateWoreInstead('o1'), { items: ['i1'] }),
      [
        ['outfits'],
        ['outfit', 'o1'],
        ['pendingOutfits'],
        ['calendarOutfits'],
        ['analytics'],
        ['learning'],
        ...EVERY_ITEM_WEAR,
      ],
    ],
    [
      'useWearToday',
      () => invalidatedKeys(() => useWearToday('o1'), {}),
      [['outfits'], ['calendarOutfits'], ...EVERY_ITEM_WEAR],
    ],
    ['useDeleteOutfit', () => invalidatedKeys(useDeleteOutfit, 'o1'), OUTFIT_LISTS],
    [
      'useBulkDeleteOutfits',
      () => invalidatedKeys(useBulkDeleteOutfits, { outfit_ids: ['o1'] }),
      OUTFIT_LISTS,
    ],
  ])('%s invalidates the same keys', async (_name, run, expected) => {
    expect(await run()).toEqual(expected)
  })
})
