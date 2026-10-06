import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import {
  useRemoveBackground,
  useReplaceItemImage,
  useRestoreOriginal,
  useRotateImage,
  useSetPrimaryImage,
} from '@/lib/hooks/use-items'

vi.mock('@/lib/api', () => ({
  api: { post: vi.fn().mockResolvedValue({}), delete: vi.fn().mockResolvedValue(undefined) },
  getAccessToken: vi.fn(() => null),
  setAccessToken: vi.fn(),
  ApiError: class extends Error {},
  NetworkError: class extends Error {},
}))

const PRIMARY_IMAGE_KEYS = [['items'], ['item', 'item-1'], ['outfits'], ['calendarOutfits']]

function setup() {
  const client = new QueryClient()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { invalidate, wrapper }
}

type Wrapper = ReturnType<typeof setup>['wrapper']

async function mutate<V>(
  useHook: () => { mutateAsync: (variables: V) => Promise<unknown> },
  wrapper: Wrapper,
  variables: V
) {
  const { result } = renderHook(useHook, { wrapper })
  await act(async () => {
    await result.current.mutateAsync(variables)
  })
}

function invalidatedKeys(invalidate: ReturnType<typeof setup>['invalidate']) {
  return invalidate.mock.calls.map(([filters]) => filters?.queryKey)
}

afterEach(() => {
  vi.mocked(api.post).mockClear()
  vi.restoreAllMocks()
})

describe('mutations that change an item primary image', () => {
  const cases: Array<[string, (wrapper: Wrapper) => Promise<unknown>]> = [
    [
      'set primary',
      (wrapper) =>
        mutate(() => useSetPrimaryImage(), wrapper, { itemId: 'item-1', imageId: 'img-2' }),
    ],
    ['rotate', (wrapper) => mutate(() => useRotateImage(), wrapper, { id: 'item-1', direction: 'cw' })],
    ['remove background', (wrapper) => mutate(() => useRemoveBackground(), wrapper, { id: 'item-1' })],
    ['restore original', (wrapper) => mutate(() => useRestoreOriginal(), wrapper, 'item-1')],
    [
      'replace image',
      (wrapper) => {
        vi.spyOn(global, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }))
        return mutate(() => useReplaceItemImage(), wrapper, {
          itemId: 'item-1',
          file: new File(['x'], 'a.jpg'),
        })
      },
    ],
  ]

  it.each(cases)('%s refreshes item and outfit caches', async (_name, run) => {
    const { invalidate, wrapper } = setup()
    await run(wrapper)
    expect(invalidatedKeys(invalidate)).toEqual(expect.arrayContaining(PRIMARY_IMAGE_KEYS))
  })
})
