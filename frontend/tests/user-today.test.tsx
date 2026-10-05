import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { useUserToday } from '@/lib/hooks/use-user'
import { getTodayDateStringInTimezone } from '@/lib/utils'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
  setAccessToken: vi.fn(),
}))

// 20:00 on 5 October in Los Angeles (PDT, UTC-7) is already 6 October in UTC.
const LA_EVENING = new Date('2026-10-06T03:00:00Z')

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(LA_EVENING)
})

afterEach(() => {
  vi.useRealTimers()
  vi.mocked(api.get).mockReset()
})

describe('getTodayDateStringInTimezone', () => {
  it('returns the local calendar day, not the UTC one', () => {
    expect(new Date().toISOString().slice(0, 10)).toBe('2026-10-06')
    expect(getTodayDateStringInTimezone('America/Los_Angeles')).toBe('2026-10-05')
  })

  it('reads the day in zones ahead of UTC too', () => {
    expect(getTodayDateStringInTimezone('Pacific/Auckland')).toBe('2026-10-06')
  })
})

describe('useUserToday', () => {
  it("dates by the user's profile timezone", async () => {
    vi.mocked(api.get).mockResolvedValue({ timezone: 'America/Los_Angeles' })
    const { result } = renderHook(() => useUserToday(), { wrapper })
    await waitFor(() => expect(result.current()).toBe('2026-10-05'))
  })

  it('falls back to the browser timezone until the profile loads', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useUserToday(), { wrapper })
    const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone
    expect(result.current()).toBe(getTodayDateStringInTimezone(browserZone))
  })
})
