import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AcceptanceTrendChart } from '@/components/acceptance-trend-chart'

vi.mock('next-intl', () => ({
  useLocale: () => 'de',
  useTranslations: () => (key: string) => key,
}))

describe('AcceptanceTrendChart', () => {
  it('labels each week from its ISO start date on the app locale', () => {
    render(
      <AcceptanceTrendChart
        data={[
          { period: 'Oct 06', period_start: '2026-10-06', total: 2, accepted: 1, rejected: 1, rate: 50 },
        ]}
      />,
    )

    const expected = new Date(2026, 9, 6).toLocaleDateString('de', { month: 'short', day: 'numeric' })
    expect(screen.getByText(expected)).toBeInTheDocument()
    expect(screen.queryByText('Oct 06')).not.toBeInTheDocument()
  })
})
