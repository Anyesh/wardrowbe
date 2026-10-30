import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, renderHook, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { OccasionChips } from '@/components/shared/occasion-chips'
import { useOccasionOptions } from '@/lib/hooks/use-translated-constants'
import { FEATURED_OCCASIONS } from '@/lib/types'

vi.unmock('next-intl')

const constants = JSON.parse(
  readFileSync(resolve(__dirname, '..', 'messages', 'de', 'constants.json'), 'utf8'),
)

function wrapper({ children }: { children: ReactNode }) {
  return (
    <NextIntlClientProvider locale="de" messages={{ constants }}>
      {children}
    </NextIntlClientProvider>
  )
}

describe('useOccasionOptions', () => {
  it('lists only the featured occasions when every kept value is featured', () => {
    const { result } = renderHook(() => useOccasionOptions(['casual', null, undefined]), { wrapper })
    expect(result.current.map((o) => o.value)).toEqual(FEATURED_OCCASIONS.map((o) => o.value))
  })

  it('appends a stored non-featured occasion once, with its label', () => {
    const { result } = renderHook(() => useOccasionOptions(['wedding', 'wedding']), { wrapper })
    const extra = result.current.slice(FEATURED_OCCASIONS.length)
    expect(extra).toEqual([{ value: 'wedding', label: constants.occasions.wedding }])
  })
})

describe('OccasionChips', () => {
  it('shows a selected non-featured occasion as a selected chip', () => {
    render(<OccasionChips selected="wedding" onSelect={() => {}} />, { wrapper })
    const chip = screen.getByRole('button', { name: constants.occasions.wedding })
    expect(chip).toHaveAttribute('data-selected', 'true')
  })

  it('keeps the stored occasion after another chip is picked', () => {
    render(<OccasionChips selected="casual" extraOccasions={['wedding']} onSelect={() => {}} />, {
      wrapper,
    })
    expect(screen.getByRole('button', { name: constants.occasions.wedding })).toHaveAttribute(
      'data-selected',
      'false',
    )
  })
})
