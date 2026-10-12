import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import HistoryPage from '@/app/dashboard/history/page'
import { OutfitCalendar } from '@/components/outfit-calendar'
import { OutfitCard } from '@/components/outfits/outfit-card'
import type { Outfit } from '@/lib/hooks/use-outfits'

const intl = vi.hoisted(() => ({ locale: 'en' }))

// The global stub in tests/setup.ts drops message params, so the date passed to
// t() would be invisible; this one echoes them back.
vi.mock('next-intl', () => ({
  useLocale: () => intl.locale,
  useTranslations: () =>
    Object.assign(
      (key: string, params?: Record<string, unknown>) =>
        params && 'date' in params ? `${key}: ${params.date}` : key,
      { has: () => false },
    ),
}))

const calendarOutfits = vi.hoisted(() => ({
  outfits: [{ id: 'o1', scheduled_for: '2026-10-02', source: 'scheduled', occasion: 'casual' }],
}))

vi.mock('@/lib/hooks/use-outfits', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/hooks/use-outfits')>()),
  useCalendarOutfits: () => ({ data: calendarOutfits, isLoading: false, isError: false }),
}))

vi.mock('@/lib/hooks/use-user', () => ({
  useUserToday: () => () => '2026-10-05',
}))

const CASES = [
  {
    locale: 'en',
    heading: 'Monday, October 5',
    emptyDate: 'noOutfitsForDate: October 5, 2026',
    month: 'October 2026',
    relative: 'in 3 days',
  },
  {
    locale: 'de',
    heading: 'Montag, 5. Oktober',
    emptyDate: 'noOutfitsForDate: 5. Oktober 2026',
    month: 'Oktober 2026',
    relative: 'in 3 Tagen',
  },
  {
    locale: 'ja',
    heading: '10月5日月曜日',
    emptyDate: 'noOutfitsForDate: 2026年10月5日',
    month: '2026年10月',
    relative: '3 日後',
  },
]

const TODAY = { en: 'today', de: 'heute', ja: '今日' }

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 9, 5, 12))
})

afterEach(() => {
  vi.useRealTimers()
  intl.locale = 'en'
})

describe.each(CASES)('date displays under $locale', ({ locale, heading, emptyDate, month, relative }) => {
  beforeEach(() => {
    intl.locale = locale
  })

  it('renders the history day heading and empty-day date on the app locale', () => {
    render(<HistoryPage />)
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(heading)
    expect(screen.getByText(emptyDate)).toBeInTheDocument()
  })

  it('renders the calendar month header on the app locale', () => {
    render(
      <OutfitCalendar
        year={2026}
        month={10}
        outfits={calendarOutfits.outfits as Outfit[]}
        selectedDate={null}
        onSelectDate={() => {}}
        onMonthChange={() => {}}
      />,
    )
    expect(screen.getByRole('heading', { level: 3 }).textContent).toBe(month)
  })

  it('renders the outfit card date relative to today on the app locale', () => {
    const outfit = { ...calendarOutfits.outfits[0], scheduled_for: '2026-10-08', name: 'n', items: [] }
    render(<OutfitCard outfit={outfit as unknown as Outfit} />)
    expect(screen.getByText(relative)).toBeInTheDocument()
  })

  it('counts the outfit card date from the profile today, not the browser day', () => {
    vi.setSystemTime(new Date(2026, 9, 9, 12))
    const outfit = { ...calendarOutfits.outfits[0], scheduled_for: '2026-10-05', name: 'n', items: [] }
    render(<OutfitCard outfit={outfit as unknown as Outfit} />)
    expect(screen.getByText(TODAY[locale as keyof typeof TODAY])).toBeInTheDocument()
  })
})
