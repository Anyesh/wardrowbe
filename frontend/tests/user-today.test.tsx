import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { useUserTimezone, useUserToday } from '@/lib/hooks/use-user'
import { getTodayDateStringInTimezone, resolveTimezone } from '@/lib/utils'

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
  it.each([
    ['2026-10-06T03:00:00Z', 'UTC', '2026-10-06'],
    ['2026-10-06T03:00:00Z', 'America/Los_Angeles', '2026-10-05'],
    ['2026-10-06T03:00:00Z', 'Pacific/Auckland', '2026-10-06'],
    ['2026-10-05T10:59:00Z', 'Pacific/Tongatapu', '2026-10-05'],
    ['2026-10-05T11:00:00Z', 'Pacific/Tongatapu', '2026-10-06'],
    ['2026-10-05T18:14:00Z', 'Asia/Kathmandu', '2026-10-05'],
    ['2026-10-05T18:15:00Z', 'Asia/Kathmandu', '2026-10-06'],
    ['2026-03-08T06:59:00Z', 'America/New_York', '2026-03-08'],
    ['2026-03-08T04:59:00Z', 'America/New_York', '2026-03-07'],
  ])('at %s the day in %s is %s', (instant, zone, day) => {
    vi.setSystemTime(new Date(instant))
    expect(getTodayDateStringInTimezone(zone)).toBe(day)
  })
})

describe('resolveTimezone', () => {
  it.each([
    ['Asia/Kathmandu', 'Asia/Kathmandu'],
    ['Mars/Olympus_Mons', 'UTC'],
    ['', 'UTC'],
    [null, 'UTC'],
    [undefined, 'UTC'],
  ])('resolves %j to %s, as the backend does', (name, zone) => {
    expect(resolveTimezone(name)).toBe(zone)
  })
})

describe('useUserToday', () => {
  it("dates by the user's profile timezone", async () => {
    vi.mocked(api.get).mockResolvedValue({ timezone: 'America/Los_Angeles' })
    const { result } = renderHook(() => useUserToday(), { wrapper })
    await waitFor(() => expect(result.current()).toBe('2026-10-05'))
  })

  it('dates by UTC until the profile loads, as the backend does without a zone', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useUserToday(), { wrapper })
    expect(result.current()).toBe('2026-10-06')
  })
})

describe('useUserTimezone', () => {
  it.each([
    ['America/Los_Angeles', 'America/Los_Angeles'],
    ['Mars/Olympus_Mons', 'UTC'],
  ])('reads the stored zone %s as %s', async (stored, zone) => {
    vi.mocked(api.get).mockResolvedValue({ timezone: stored })
    const { result } = renderHook(() => useUserTimezone(), { wrapper })
    await waitFor(() => expect(api.get).toHaveBeenCalled())
    await waitFor(() => expect(result.current).toBe(zone))
  })

  it('is UTC until the profile loads', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useUserTimezone(), { wrapper })
    expect(result.current).toBe('UTC')
  })
})
