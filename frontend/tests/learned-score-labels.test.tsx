import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import LearningPage from '@/app/dashboard/learning/page'

vi.unmock('next-intl')

const learningData = vi.hoisted(() => ({
  profile: {
    has_learning_data: true,
    feedback_count: 3,
    outfits_rated: 3,
    overall_acceptance_rate: null,
    average_rating: null,
    average_comfort_rating: null,
    average_style_rating: null,
    color_preferences: [
      { color: 'navy', score: 0.6, interpretation: 'strongly liked', interpretation_key: 'stronglyLiked' },
      { color: 'orange', score: -0.3, interpretation: 'disliked' },
    ],
    style_preferences: [{ style: 'minimalist', score: 0.4 }],
    occasion_patterns: [],
    weather_preferences: [{ weather_type: 'cold', preferred_layers: 2.5, success_rate: 0.8 }],
    last_computed_at: null,
  },
  best_pairs: [],
  insights: [],
  preference_suggestions: { updated: false },
}))

vi.mock('@/lib/hooks/use-learning', () => {
  const mutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }
  return {
    useLearning: () => ({ data: learningData, isLoading: false, isError: false }),
    useRecomputeLearning: () => mutation,
    useGenerateInsights: () => mutation,
    useAcknowledgeInsight: () => mutation,
  }
})

function messages(locale: string, namespace: string) {
  return JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', locale, `${namespace}.json`), 'utf8'),
  )
}

function wrapperFor(locale: string, namespaces: string[]) {
  const all = Object.fromEntries(namespaces.map((ns) => [ns, messages(locale, ns)]))
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={all} onError={() => {}}>
        {children}
      </NextIntlClientProvider>
    )
  }
}

describe('learned score labels', () => {
  it('translate interpretations, styles and weather types', () => {
    render(<LearningPage />, { wrapper: wrapperFor('de', ['learning', 'constants', 'common']) })
    const learning = messages('de', 'learning')
    const constants = messages('de', 'constants')

    expect(screen.getByText(learning.interpretationStronglyLiked)).toBeInTheDocument()
    expect(screen.queryByText('strongly liked')).not.toBeInTheDocument()
    expect(screen.getByText(constants.styles.minimalist)).toBeInTheDocument()
    expect(screen.getByText(learning.weatherTypeCold)).toBeInTheDocument()
  })

  it('keep the English interpretation from an API without interpretation_key', () => {
    render(<LearningPage />, { wrapper: wrapperFor('de', ['learning', 'constants', 'common']) })
    expect(screen.getByText('disliked')).toBeInTheDocument()
  })
})
