import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import HistoryPage from '@/app/dashboard/history/page'
import OutfitsPage from '@/app/dashboard/outfits/page'
import { useCalendarOutfits } from '@/lib/hooks/use-outfits'

const calendarProps = vi.hoisted(() => [] as { year: number; month: number; selectedDate: Date | null }[])

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
  setAccessToken: vi.fn(),
}))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/dashboard/outfits',
  useSearchParams: () => new URLSearchParams('view=calendar'),
}))
vi.mock('@/lib/hooks/use-outfits', () => {
  const empty = { data: { outfits: [], total: 0, has_more: false }, isLoading: false, isError: false }
  return {
    useCalendarOutfits: vi.fn(() => empty),
    useOutfits: () => empty,
    useBulkDeleteOutfits: () => ({ mutateAsync: vi.fn(), isPending: false }),
  }
})
vi.mock('@/components/outfit-calendar', () => ({
  OutfitCalendar: (props: { year: number; month: number; selectedDate: Date | null }) => {
    calendarProps.push(props)
    return null
  },
}))

const originalTz = process.env.TZ

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  client.setQueryData(['user-profile'], { timezone: 'America/Los_Angeles' })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  process.env.TZ = 'UTC'
  vi.useFakeTimers({ toFake: ['Date'] })
  // Already 1 November in the browser's UTC clock, still 31 October in Los Angeles.
  vi.setSystemTime(new Date('2026-11-01T03:00:00Z'))
  calendarProps.length = 0
})

afterEach(() => {
  vi.useRealTimers()
  process.env.TZ = originalTz
  vi.mocked(useCalendarOutfits).mockClear()
})

describe("calendars start on the user's day", () => {
  it('opens history on the profile month and selects the profile day', () => {
    render(<HistoryPage />, { wrapper })

    expect(useCalendarOutfits).toHaveBeenLastCalledWith(2026, 10, {})
    const last = calendarProps[calendarProps.length - 1]
    expect(last.year).toBe(2026)
    expect(last.month).toBe(10)
    expect(last.selectedDate?.getDate()).toBe(31)
    expect(last.selectedDate?.getMonth()).toBe(9)
  })

  it('opens the outfits calendar on the profile month', () => {
    render(<OutfitsPage />, { wrapper })

    expect(vi.mocked(useCalendarOutfits).mock.lastCall?.slice(0, 2)).toEqual([2026, 10])
    const last = calendarProps[calendarProps.length - 1]
    expect([last.year, last.month]).toEqual([2026, 10])
  })
})
