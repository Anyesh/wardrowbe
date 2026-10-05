import { render, screen } from '@testing-library/react'
import type { ComponentType } from 'react'
import { describe, expect, it, vi } from 'vitest'
import AnalyticsPage from '@/app/dashboard/analytics/page'
import DashboardPage from '@/app/dashboard/page'
import LearningPage from '@/app/dashboard/learning/page'
import { useAnalytics } from '@/lib/hooks/use-analytics'
import { useLearning } from '@/lib/hooks/use-learning'

vi.mock('next/image', () => ({ default: () => null }))
vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useColorLabel: () => (c: string) => c,
  useOccasionLabel: () => (o: string) => o,
  useWeatherConditionLabel: () => (c: string) => c,
  useStyleLabel: () => (s: string) => s,
}))
vi.mock('@/lib/hooks/use-analytics', () => ({ useAnalytics: vi.fn() }))
vi.mock('@/lib/hooks/use-learning', () => ({
  useLearning: vi.fn(),
  useRecomputeLearning: () => ({ mutateAsync: vi.fn() }),
  useGenerateInsights: () => ({ mutateAsync: vi.fn() }),
  useAcknowledgeInsight: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/lib/hooks/use-weather', () => ({
  useWeather: () => ({ data: undefined, isLoading: false, isError: true }),
}))
vi.mock('@/lib/hooks/use-preferences', () => ({ usePreferences: () => ({ data: undefined }) }))
vi.mock('@/lib/hooks/use-outfits', () => ({
  usePendingOutfits: () => ({ data: undefined, isLoading: false }),
  useAcceptOutfit: () => ({ mutate: vi.fn() }),
  useRejectOutfit: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/lib/hooks/use-notifications', () => ({
  useSchedules: () => ({ data: [], isLoading: false }),
  useNotificationSettings: () => ({ data: undefined, isLoading: false }),
}))
vi.mock('@/lib/hooks/use-family', () => ({ useFamily: () => ({ data: null, isLoading: false }) }))
vi.mock('@/lib/hooks/use-user', () => ({ useUserTimezone: () => 'UTC' }))

const analytics = (acceptance: number | null, rating: number | null) => ({
  wardrobe: {
    total_items: 4,
    items_by_status: { ready: 4 },
    total_outfits: 2,
    outfits_this_week: 1,
    outfits_this_month: 2,
    acceptance_rate: acceptance,
    average_rating: rating,
    total_wears: 3,
  },
  color_distribution: [],
  type_distribution: [],
  most_worn: [],
  least_worn: [],
  never_worn: [],
  acceptance_trend: [],
  insights: [],
})

const learning = (acceptance: number | null, rating: number | null) => ({
  profile: {
    has_learning_data: true,
    feedback_count: 2,
    outfits_rated: 2,
    overall_acceptance_rate: acceptance,
    average_rating: rating,
    average_comfort_rating: null,
    average_style_rating: rating,
    color_preferences: [],
    style_preferences: [],
    occasion_patterns: [],
    weather_preferences: [],
    last_computed_at: null,
  },
  best_pairs: [],
  insights: [],
  preference_suggestions: { updated: false },
})

const setAnalytics = (acceptance: number | null, rating: number | null) =>
  vi.mocked(useAnalytics).mockReturnValue({
    data: analytics(acceptance, rating),
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useAnalytics>)

const setLearning = (acceptance: number | null, rating: number | null) =>
  vi.mocked(useLearning).mockReturnValue({
    data: learning(acceptance, rating),
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useLearning>)

interface Row {
  page: string
  Page: ComponentType
  setup: (acceptance: number | null, rating: number | null) => void
  hasData: string[]
  noData: string[]
}

const rows: Row[] = [
  {
    page: 'analytics',
    Page: AnalyticsPage,
    setup: setAnalytics,
    hasData: ['stats.acceptanceRate.description', 'stats.avgRating'],
    noData: ['stats.totalWears.noData', 'stats.totalWears.description'],
  },
  {
    page: 'dashboard',
    Page: DashboardPage,
    setup: setAnalytics,
    hasData: ['weeklySummary.avgRatingValue'],
    noData: [],
  },
  {
    page: 'learning',
    Page: LearningPage,
    setup: setLearning,
    hasData: [
      'stats.suggestionsAccepted',
      'stats.outOfStars',
      'stats.styleSatisfaction',
    ],
    noData: ['stats.notEnoughData', 'stats.rateMoreOutfits', 'stats.rateOutfitStyles'],
  },
]

describe('zero acceptance rate and rating', () => {
  it.each(rows)('$page page shows 0 as data', ({ Page, setup, hasData, noData }) => {
    setup(0, 0)
    render(<Page />)

    hasData.forEach((key) => expect(screen.getByText(key)).toBeInTheDocument())
    noData.forEach((key) => expect(screen.queryByText(key)).not.toBeInTheDocument())
  })

  it('dashboard weekly summary shows 0% and not a dash or a bare 0', () => {
    setAnalytics(0, 0)
    render(<DashboardPage />)

    expect(screen.getByText('0%')).toBeInTheDocument()
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })
})

describe('null acceptance rate and rating', () => {
  it.each(rows)('$page page shows no data', ({ Page, setup, hasData, noData }) => {
    setup(null, null)
    render(<Page />)

    hasData.forEach((key) => expect(screen.queryByText(key)).not.toBeInTheDocument())
    noData.forEach((key) => expect(screen.getByText(key)).toBeInTheDocument())
  })
})
