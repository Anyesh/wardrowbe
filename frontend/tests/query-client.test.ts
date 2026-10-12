import { describe, it, expect, vi, beforeEach } from 'vitest'
import { toast } from 'sonner'
import type { QueryClient } from '@tanstack/react-query'
import { createQueryClient } from '@/lib/query-client'
import { ApiError, NetworkError } from '@/lib/api'

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

type Meta = { toastsOwnErrors: boolean } | undefined

const failWith = (client: QueryClient, kind: 'mutation' | 'query', meta: Meta) => {
  const fail = () => Promise.reject(new ApiError('Validation error', 422, {}))
  if (kind === 'mutation') {
    return client.getMutationCache().build(client, { mutationFn: fail, meta }).execute(undefined)
  }
  return client.fetchQuery({ queryKey: ['failing'], queryFn: fail, meta })
}

const toastText = (error: unknown) => `translated: ${(error as Error).message}`

describe('global error toast', () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear()
  })

  it.each([
    { kind: 'mutation', meta: undefined, toasts: [['translated: Validation error']] },
    { kind: 'mutation', meta: { toastsOwnErrors: true }, toasts: [] },
    { kind: 'query', meta: undefined, toasts: [['translated: Validation error']] },
    { kind: 'query', meta: { toastsOwnErrors: true }, toasts: [] },
  ] as const)('$kind with meta $meta toasts $toasts', async ({ kind, meta, toasts }) => {
    const client = createQueryClient(toastText)

    await expect(failWith(client, kind, meta)).rejects.toThrow('Validation error')

    expect(vi.mocked(toast.error).mock.calls).toEqual(toasts)
  })

  it('never toasts a sign-in redirect', async () => {
    const client = createQueryClient(toastText)
    const fail = () => Promise.reject(new ApiError('Unauthorized', 401, {}))
    await expect(client.fetchQuery({ queryKey: ['auth'], queryFn: fail })).rejects.toThrow()
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('toasts network errors through the translator', async () => {
    const client = createQueryClient(toastText)
    const fail = () => Promise.reject(new NetworkError('offline'))
    await expect(client.fetchQuery({ queryKey: ['net'], queryFn: fail })).rejects.toThrow()
    expect(vi.mocked(toast.error).mock.calls).toEqual([[toastText(new NetworkError('offline'))]])
  })
})
