import { describe, it, expect, vi, beforeEach } from 'vitest'
import { toast } from 'sonner'
import { createQueryClient } from '@/lib/query-client'
import { ApiError } from '@/lib/api'

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

describe('global mutation error toast', () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear()
  })

  it.each([
    { name: 'toasts the server message by default', meta: undefined, toasts: [['Validation error']] },
    { name: 'stays quiet for a caller that toasts its own errors', meta: { toastsOwnErrors: true }, toasts: [] },
  ])('$name', async ({ meta, toasts }) => {
    const client = createQueryClient()
    const mutation = client.getMutationCache().build(client, {
      mutationFn: () => Promise.reject(new ApiError('Validation error', 422, {})),
      meta,
    })

    await expect(mutation.execute(undefined)).rejects.toThrow('Validation error')

    expect(vi.mocked(toast.error).mock.calls).toEqual(toasts)
  })
})
