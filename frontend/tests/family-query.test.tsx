import { renderHook, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '@/lib/api'
import { useFamily } from '@/lib/hooks/use-family'
import { createQueryClient } from '@/lib/query-client'

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { accessToken: 'jwt' }, status: 'authenticated' }),
}))

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn() },
  setAccessToken: vi.fn(),
}))

function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client: createQueryClient() }, children)
}

describe('useFamily', () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear()
  })

  it('reads a user without a family as no family, without a toast', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new ApiError('You are not in a family', 404, {}))

    const { result } = renderHook(() => useFamily(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBeNull()
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('still reports a failure that is not a missing family', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new ApiError('Validation error', 422, {}))

    const { result } = renderHook(() => useFamily(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('Validation error')
  })
})
