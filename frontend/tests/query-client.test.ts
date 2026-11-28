import { describe, it, expect, vi, beforeEach } from 'vitest'
import { toast } from 'sonner'
import type { QueryClient } from '@tanstack/react-query'
import { createQueryClient } from '@/lib/query-client'
import { ApiError, NetworkError } from '@/lib/api'

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

const translate = (error: unknown) =>
  error instanceof ApiError ? `translated ${error.code}` : 'translated network'

type Meta = { toastsOwnErrors: boolean } | undefined

const failWith = (client: QueryClient, kind: 'mutation' | 'query', meta: Meta) => {
  const fail = () =>
    Promise.reject(new ApiError('Validation error', 422, { error_code: 'VALIDATION_ERROR' }))
  if (kind === 'mutation') {
    return client.getMutationCache().build(client, { mutationFn: fail, meta }).execute(undefined)
  }
  return client.fetchQuery({ queryKey: ['failing'], queryFn: fail, meta })
}

describe('global error toast', () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear()
  })

  it.each([
    { kind: 'mutation', meta: undefined, toasts: [['translated VALIDATION_ERROR']] },
    { kind: 'mutation', meta: { toastsOwnErrors: true }, toasts: [] },
    { kind: 'query', meta: undefined, toasts: [['translated VALIDATION_ERROR']] },
    { kind: 'query', meta: { toastsOwnErrors: true }, toasts: [] },
  ] as const)('$kind with meta $meta toasts $toasts', async ({ kind, meta, toasts }) => {
    const client = createQueryClient(translate)

    await expect(failWith(client, kind, meta)).rejects.toThrow('Validation error')

    expect(vi.mocked(toast.error).mock.calls).toEqual(toasts)
  })
})

describe('global error toast content', () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear()
  })

  const run = (error: Error) =>
    createQueryClient(translate)
      .fetchQuery({ queryKey: ['x'], queryFn: () => Promise.reject(error), retry: false })
      .catch(() => undefined)

  it('stays silent on 401', async () => {
    await run(new ApiError('Not authenticated', 401, { error_code: 'NOT_AUTHENTICATED' }))

    expect(toast.error).not.toHaveBeenCalled()
  })

  it('shows the translated network message, not the English one', async () => {
    await run(new NetworkError('offline'))

    expect(vi.mocked(toast.error).mock.calls).toEqual([['translated network']])
  })

  it('keeps 503 toasts on screen longer', async () => {
    await run(new ApiError('AI is off', 503, { error_code: 'AI_DISABLED' }))

    expect(vi.mocked(toast.error).mock.calls).toEqual([
      ['translated AI_DISABLED', { duration: 8000 }],
    ])
  })
})
