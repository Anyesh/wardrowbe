import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CloneToLookbookDialog } from '@/components/shared/clone-to-lookbook-dialog'

// tests/setup.ts stubs next-intl globally and drops message params, which would hide the name.
vi.unmock('next-intl')

const messagesFor = (locale: string) =>
  Object.fromEntries(
    ['common', 'constants', 'outfits'].map((ns) => [
      ns,
      JSON.parse(readFileSync(resolve(__dirname, '..', 'messages', locale, `${ns}.json`), 'utf8')),
    ]),
  )

function renderDialog(locale: string, occasion: string) {
  const client = new QueryClient()
  const tree = (open: boolean) => (
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale={locale} messages={messagesFor(locale)}>
        <CloneToLookbookDialog open={open} sourceOutfitId="o1" sourceOccasion={occasion} onClose={() => {}} />
      </NextIntlClientProvider>
    </QueryClientProvider>
  )
  const view = render(tree(true))
  return {
    input: () =>
      screen.getByLabelText(messagesFor(locale).outfits.cloneToLookbook.name) as HTMLInputElement,
    setOpen: (open: boolean) => view.rerender(tree(open)),
  }
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 9, 5, 12))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('CloneToLookbookDialog default name', () => {
  it.each([
    ['en', 'Business casual · Oct 5'],
    ['de', 'Business Casual · 5. Okt.'],
    ['ja', 'ビジネスカジュアル・10月5日'],
  ])('uses the translated occasion and date in %s', (locale, expected) => {
    expect(renderDialog(locale, 'business-casual').input().value).toBe(expected)
  })

  it('falls back to a humanised occasion the catalog does not know', () => {
    expect(renderDialog('en', 'garden-party').input().value).toBe('Garden party · Oct 5')
  })

  it('recomputes the default name each time it opens', () => {
    const dialog = renderDialog('en', 'business-casual')
    fireEvent.change(dialog.input(), { target: { value: 'Edited' } })
    dialog.setOpen(false)
    vi.setSystemTime(new Date(2026, 9, 6, 12))
    dialog.setOpen(true)

    expect(dialog.input().value).toBe('Business casual · Oct 6')
  })
})
