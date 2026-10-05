import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, renderHook, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import LearningPage from '@/app/dashboard/learning/page'
import { useOccasionLabel, useWeatherConditionLabel } from '@/lib/hooks/use-translated-constants'

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
    occasion_patterns: [{ occasion: 'business-casual', preferred_colors: [], success_rate: 0.5 }],
    weather_preferences: [],
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

function backendWeatherConditions(): string[] {
  const source = readFileSync(
    resolve(__dirname, '..', '..', 'backend', 'app', 'services', 'weather_service.py'),
    'utf8',
  )
  const table = source.slice(source.indexOf('WMO_CODES = {'), source.indexOf('}', source.indexOf('WMO_CODES = {')))
  return Array.from(table.matchAll(/^\s+\d+: "([^"]+)",$/gm), (m) => m[1])
}

describe('weather condition labels', () => {
  it('has a label for every condition the backend sends', () => {
    const conditions = backendWeatherConditions()
    expect(conditions.length).toBeGreaterThan(20)
    const { result } = renderHook(() => useWeatherConditionLabel(), {
      wrapper: wrapperFor('en', ['constants']),
    })
    const known = Object.keys(messages('en', 'constants').weatherConditions)
    for (const condition of [...conditions, 'unknown']) {
      expect(known, condition).toContain(condition.replace(/\s+/g, '-'))
      expect(result.current(condition)).not.toContain('weatherConditions')
    }
  })

  it('translates multi-word conditions and the override value', () => {
    const { result } = renderHook(() => useWeatherConditionLabel(), {
      wrapper: wrapperFor('de', ['constants']),
    })
    expect(result.current('partly cloudy')).toBe('Teils bewölkt')
    expect(result.current('Cloudy')).toBe('Bewölkt')
    expect(result.current('rainy')).toBe('Regen')
  })
})

describe('occasion labels', () => {
  it('match a space-separated value to the hyphenated key', () => {
    const { result } = renderHook(() => useOccasionLabel(), {
      wrapper: wrapperFor('de', ['constants']),
    })
    expect(result.current('business casual')).toBe(messages('de', 'constants').occasions['business-casual'])
  })

  it('labels learned occasion patterns', () => {
    render(<LearningPage />, { wrapper: wrapperFor('de', ['learning', 'constants', 'common']) })
    expect(screen.getByText(messages('de', 'constants').occasions['business-casual'])).toBeInTheDocument()
    expect(screen.queryByText('business-casual')).not.toBeInTheDocument()
  })
})
