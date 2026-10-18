import { renderHook, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'
import { ApiError, api } from '@/lib/api'
import { queryKeys } from '@/lib/hooks/query-keys'
import { useFamily } from '@/lib/hooks/use-family'
import { createQueryClient } from '@/lib/query-client'

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { accessToken: 'jwt' }, status: 'authenticated' }),
}))

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn() },
  setAccessToken: vi.fn(),
}))

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

function renderUseFamily() {
  const client = createQueryClient()
  client.setQueryDefaults(queryKeys.family, { retryDelay: 0 })
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children)
  return renderHook(() => useFamily(), { wrapper })
}

describe('useFamily', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('answers null without a toast when the user is not in a family', async () => {
    vi.mocked(api.get).mockRejectedValue(new ApiError('You are not in a family', 404, {}))

    const { result } = renderUseFamily()

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBeNull()
    expect(api.get).toHaveBeenCalledWith('/families/me')
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('still toasts a real failure', async () => {
    vi.mocked(api.get).mockRejectedValue(new ApiError('Internal server error', 500, {}))

    const { result } = renderUseFamily()

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('Internal server error')
  })
})
