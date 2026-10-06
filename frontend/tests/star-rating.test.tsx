import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { StarRatingDisplay, StarRatingInput } from '@/components/shared/star-rating'
import { RATING_MAX } from '@/lib/generated/scales'
import { sourceFiles } from './source-files'

vi.unmock('next-intl')

const common = JSON.parse(
  readFileSync(resolve(__dirname, '..', 'messages', 'en', 'common.json'), 'utf8'),
)

function wrapper({ children }: { children: ReactNode }) {
  return (
    <NextIntlClientProvider locale="en" messages={{ common }}>
      {children}
    </NextIntlClientProvider>
  )
}

describe('StarRatingInput', () => {
  it('names each star button with a plural-aware label and marks the chosen one pressed', () => {
    render(<StarRatingInput value={3} onChange={() => {}} />, { wrapper })

    expect(screen.getByRole('button', { name: 'Rate 1 star' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Rate 3 stars' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getAllByRole('button')).toHaveLength(RATING_MAX)
  })

  it('reports the clicked star', () => {
    const onChange = vi.fn()
    render(<StarRatingInput value={0} onChange={onChange} />, { wrapper })

    fireEvent.click(screen.getByRole('button', { name: `Rate ${RATING_MAX} stars` }))

    expect(onChange).toHaveBeenCalledWith(RATING_MAX)
  })
})

describe('StarRatingDisplay', () => {
  it('reads as one image with the rating out of the maximum', () => {
    render(<StarRatingDisplay value={4} />, { wrapper })
    expect(screen.getByRole('img', { name: `Rated 4 stars out of ${RATING_MAX}` })).toBeInTheDocument()
  })
})

describe('star rows', () => {
  it('are all rendered through the shared star rating component', () => {
    const offenders = sourceFiles()
      .filter((f) => f.path !== 'components/shared/star-rating.tsx' && f.path !== 'lib/rating.ts')
      .filter((f) => f.text.includes('RATING_STARS'))
      .map((f) => f.path)
    expect(offenders).toEqual([])
  })
})
