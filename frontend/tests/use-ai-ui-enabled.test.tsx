import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { queryKeys } from '@/lib/hooks/query-keys'
import { useAiUiEnabled } from '@/lib/hooks/use-features'

describe('useAiUiEnabled', () => {
  it('keeps the AI UI hidden when a later refetch of the features fails', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(queryKeys.features, {
      background_removal: false,
      max_upload_size_mb: 20,
      ai_ui_enabled: false,
    })
    global.fetch = vi.fn(() => Promise.reject(new TypeError('offline'))) as unknown as typeof fetch
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useAiUiEnabled(), { wrapper })
    expect(result.current).toBe(false)

    await act(async () => {
      await client.refetchQueries({ queryKey: queryKeys.features })
    })

    await waitFor(() => expect(client.getQueryState(queryKeys.features)?.status).toBe('error'))
    expect(result.current).toBe(false)
  })
})
