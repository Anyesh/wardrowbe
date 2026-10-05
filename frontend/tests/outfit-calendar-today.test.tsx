import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { OutfitCalendar } from '@/components/outfit-calendar'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
  setAccessToken: vi.fn(),
}))

const originalTz = process.env.TZ

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  process.env.TZ = 'UTC'
  vi.useFakeTimers({ toFake: ['Date'] })
  // Already 6 October in the browser's UTC clock, still 5 October in Los Angeles.
  vi.setSystemTime(new Date('2026-10-06T03:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
  process.env.TZ = originalTz
  vi.mocked(api.get).mockReset()
})

describe('OutfitCalendar', () => {
  it("marks today by the user's profile timezone", async () => {
    vi.mocked(api.get).mockResolvedValue({ timezone: 'America/Los_Angeles' })
    render(
      <OutfitCalendar
        year={2026}
        month={10}
        outfits={[]}
        selectedDate={null}
        onSelectDate={() => {}}
        onMonthChange={() => {}}
      />,
      { wrapper }
    )

    await waitFor(() =>
      expect(screen.getByRole('button', { name: '5' })).toHaveAttribute('aria-current', 'date')
    )
    expect(screen.getByRole('button', { name: '6' })).not.toHaveAttribute('aria-current')
  })
})
