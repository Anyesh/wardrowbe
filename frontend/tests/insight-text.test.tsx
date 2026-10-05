import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, renderHook, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import LearningPage from '@/app/dashboard/learning/page'
import { useAnalyticsInsightLines } from '@/lib/hooks/use-insight-text'

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
    color_preferences: [],
    style_preferences: [],
    occasion_patterns: [],
    weather_preferences: [],
    last_computed_at: null,
  },
  best_pairs: [],
  insights: [
    {
      id: 'keyed',
      category: 'color',
      insight_type: 'positive',
      title: 'You love navy!',
      description: 'Your feedback shows a strong preference for navy items.',
      confidence: 0.6,
      created_at: '2026-10-01T00:00:00Z',
      message_key: 'insightColorLoved',
      message_params: { color: 'navy' },
    },
    {
      id: 'legacy',
      category: 'weather',
      insight_type: 'pattern',
      title: 'Legacy English title',
      description: 'Legacy English description',
      confidence: 0.5,
      created_at: '2026-10-01T00:00:00Z',
      message_key: null,
      message_params: {},
    },
  ],
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

function backendSource(...path: string[]) {
  return readFileSync(resolve(__dirname, '..', '..', 'backend', 'app', ...path), 'utf8')
}

describe('insight keys the backend sends', () => {
  it('each have an analytics message', () => {
    const table = backendSource('api', 'analytics.py').split('_INSIGHT_TEXT_EN')[1]
    const keys = new Set(
      Array.from(table.matchAll(/"(insight\w+?)(?:_one|_other)?":/g), (m) => m[1]),
    )
    expect(keys.size).toBeGreaterThan(5)
    const analytics = messages('en', 'analytics')
    for (const key of Array.from(keys)) expect(analytics, key).toHaveProperty(key)
  })

  it('each have a learning title and description', () => {
    const source = backendSource('services', 'learning_service.py')
    const keys = Array.from(source.matchAll(/return "(insight\w+)"/g), (m) => m[1])
    expect(keys.length).toBeGreaterThan(3)
    const learning = messages('en', 'learning')
    for (const key of keys) {
      expect(learning, key).toHaveProperty(`${key}Title`)
      expect(learning, key).toHaveProperty(`${key}Description`)
    }
  })
})

describe('analytics insight lines', () => {
  it('translates keyed insights with localized params', () => {
    const { result } = renderHook(
      () =>
        useAnalyticsInsightLines({
          insights: ['You have 3 items you have never worn.', 'Heavy on navy (45.5%).'],
          insight_items: [
            { key: 'insightNeverWorn', params: { count: 3 } },
            { key: 'insightColorHeavy', params: { color: 'navy', percent: 45.5 } },
          ],
        }),
      { wrapper: wrapperFor('de', ['analytics', 'constants']) },
    )
    const navy = messages('de', 'constants').colors.navy
    expect(result.current[0]).toContain('3 Stücke')
    expect(result.current[1]).toContain(navy)
    expect(result.current[1]).toContain('45,5')
  })

  it('falls back to the English sentence for an unknown key or an older API', () => {
    const wrapper = wrapperFor('de', ['analytics', 'constants'])
    const unknown = renderHook(
      () =>
        useAnalyticsInsightLines({
          insights: ['Some new English insight'],
          insight_items: [{ key: 'insightFromTheFuture', params: {} }],
        }),
      { wrapper },
    )
    expect(unknown.result.current).toEqual(['Some new English insight'])

    const older = renderHook(() => useAnalyticsInsightLines({ insights: ['Old line'] }), { wrapper })
    expect(older.result.current).toEqual(['Old line'])
  })
})

describe('learning insight cards', () => {
  it('render keyed insights in the user language and keep the English text otherwise', () => {
    render(<LearningPage />, { wrapper: wrapperFor('de', ['learning', 'constants', 'common']) })
    const navy = messages('de', 'constants').colors.navy
    const learning = messages('de', 'learning')

    expect(screen.getByText(learning.insightColorLovedTitle.replace('{color}', navy))).toBeInTheDocument()
    expect(screen.queryByText('You love navy!')).not.toBeInTheDocument()
    expect(screen.getByText('Legacy English title')).toBeInTheDocument()
    expect(screen.getByText(learning.insightCategoryColor)).toBeInTheDocument()
    expect(screen.getByText(learning.insightCategoryWeather)).toBeInTheDocument()
  })
})
