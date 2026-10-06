import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { renderHook } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { findClothingColor, useColorLabel, useSubtypeLabel } from '@/lib/hooks/use-translated-constants'

// tests/setup.ts stubs next-intl globally; the fallback under test depends on real t.has().
vi.unmock('next-intl')

function wrapperFor(locale: string) {
  const constants = JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', locale, 'constants.json'), 'utf8'),
  )
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={{ constants }}>
        {children}
      </NextIntlClientProvider>
    )
  }
}

describe('useSubtypeLabel', () => {
  it('translates subtypes from the catalog', () => {
    const { result } = renderHook(() => useSubtypeLabel(), { wrapper: wrapperFor('de') })
    expect(result.current('turtleneck')).toBe('Rollkragen')
    expect(result.current('Turtleneck')).toBe('Rollkragen')
  })

  it('humanizes free-text subtypes the catalog does not know', () => {
    // The model and users can both write subtypes outside the suggestion list; these
    // must not render as a raw "constants.subtypes.x" key path.
    const { result } = renderHook(() => useSubtypeLabel(), { wrapper: wrapperFor('en') })
    expect(result.current('tights')).toBe('Tights')
    expect(result.current('fishnet-tights')).toBe('Fishnet tights')
  })
})

describe('stored clothing colors', () => {
  it('finds palette colors regardless of stored capitalization without changing their value', () => {
    const colors = [{ value: 'navy', name: 'Navy', hex: '#123456' }]
    expect(findClothingColor(colors, '  NaVy  ')).toBe(colors[0])
    expect(findClothingColor(colors, 'light-blue')).toBeUndefined()
  })

  it('translates known colors and makes out-of-palette values readable', () => {
    const { result } = renderHook(() => useColorLabel(), { wrapper: wrapperFor('en') })
    expect(result.current('NAVY')).toBe('Navy')
    expect(result.current('light-blue')).toBe('Light blue')
    expect(result.current('silver')).toBe('Silver')
    expect(result.current('sage_green')).toBe('Sage green')
  })
})
