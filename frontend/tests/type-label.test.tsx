import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { renderHook } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { useTypeLabel } from '@/lib/hooks/use-translated-constants'
import { sourceFiles } from './source-files'

vi.unmock('next-intl')

function wrapper({ children }: { children: ReactNode }) {
  const constants = JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', 'de', 'constants.json'), 'utf8'),
  )
  return (
    <NextIntlClientProvider locale="de" messages={{ constants }}>
      {children}
    </NextIntlClientProvider>
  )
}

describe('clothing type labels', () => {
  it('translate a stored type and humanise one outside the catalog', () => {
    const { result } = renderHook(() => useTypeLabel(), { wrapper })
    const constants = JSON.parse(
      readFileSync(resolve(__dirname, '..', 'messages', 'de', 'constants.json'), 'utf8'),
    )
    expect(result.current('pants')).toBe(constants.types.pants)
    expect(result.current('tights')).toBe('Tights')
  })

  it('are used wherever an item type is rendered as text', () => {
    const raw = /(\|\|\s*\w+\.type\s*[})])|(\{\s*\w+\.type\s*\})|(\{\w+\.primary_color\} \{\w+\.type\})/
    const offenders = sourceFiles()
      .filter((file) => file.path.endsWith('.tsx'))
      .flatMap((file) =>
        file.text
          .split('\n')
          .map((line, i) => [file.path, i + 1, line.trim()] as const)
          .filter(([, , line]) => raw.test(line) && !/key=|value=/.test(line)),
      )
    expect(offenders).toEqual([])
  })
})
