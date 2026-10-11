import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import LearningPage from '@/app/dashboard/learning/page'

vi.unmock('next-intl')
// A maximum other than 5 shows whether the copy follows the scale or repeats a literal.
vi.mock('@/lib/generated/scales', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/generated/scales')>()),
  RATING_MAX: 10,
}))

const learningData = vi.hoisted(() => ({
  profile: {
    has_learning_data: true,
    feedback_count: 4,
    outfits_rated: 4,
    overall_acceptance_rate: 0,
    average_rating: 4.2,
    average_comfort_rating: null,
    average_style_rating: null,
    color_preferences: [],
    style_preferences: [],
    occasion_patterns: [],
    weather_preferences: [] as { weather_type: string; preferred_layers: number; success_rate: number }[],
    last_computed_at: null as string | null,
  },
  best_pairs: [],
  insights: [],
  preference_suggestions: { updated: false },
}))

vi.mock('@/lib/hooks/use-user', () => ({ useUserTimezone: () => 'Asia/Tokyo' }))
vi.mock('@/lib/hooks/use-learning', () => {
  const mutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }
  return {
    useLearning: () => ({ data: learningData, isLoading: false, isError: false }),
    useRecomputeLearning: () => mutation,
    useGenerateInsights: () => mutation,
    useAcknowledgeInsight: () => mutation,
  }
})

function messages(namespace: string) {
  return JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', 'en', `${namespace}.json`), 'utf8'),
  )
}

function wrapper({ children }: { children: ReactNode }) {
  const all = Object.fromEntries(
    ['learning', 'constants', 'common'].map((ns) => [ns, messages(ns)]),
  )
  return (
    <NextIntlClientProvider locale="en" messages={all} onError={() => {}}>
      {children}
    </NextIntlClientProvider>
  )
}

describe('learning stats', () => {
  it('takes the star maximum from the rating scale', () => {
    render(<LearningPage />, { wrapper })

    expect(screen.getByText('out of 10 stars')).toBeInTheDocument()
  })

  it('capitalises only the raw weather type, not its translation', () => {
    learningData.profile.weather_preferences = [
      { weather_type: 'cold', preferred_layers: 2, success_rate: 0.5 },
      { weather_type: 'humid', preferred_layers: 1, success_rate: 0.5 },
    ]
    render(<LearningPage />, { wrapper })

    expect(screen.getByRole('heading', { name: messages('learning').weatherTypeCold })).not.toHaveClass(
      'capitalize',
    )
    expect(screen.getByRole('heading', { name: 'humid' })).toHaveClass('capitalize')
  })

  it('shows the last update in the profile timezone', () => {
    learningData.profile.last_computed_at = '2026-10-05T23:30:00Z'
    render(<LearningPage />, { wrapper })

    expect(
      screen.getByText('Learning profile last updated: 10/6/2026, 8:30:00 AM'),
    ).toBeInTheDocument()
  })
})
