import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { useState, type ReactNode } from 'react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { ItemTagsEditor } from '@/components/item-tags-editor'
import { PATTERN_VALUES } from '@/lib/generated/garment-vocabulary'
import { draftFromTags, type TagDraft } from '@/lib/tag-edits'
import type { ItemTags } from '@/lib/types'

// tests/setup.ts stubs next-intl to echo keys; these assertions need the real catalog.
vi.unmock('next-intl')

const messages = Object.fromEntries(
  ['wardrobe', 'constants', 'common'].map((ns) => [
    ns,
    JSON.parse(readFileSync(resolve(__dirname, '..', 'messages', 'en', `${ns}.json`), 'utf8')),
  ]),
)

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <NextIntlClientProvider locale="en" messages={messages} onError={() => {}}>
      {children}
    </NextIntlClientProvider>
  )
}

beforeAll(() => {
  // Radix Select calls these on open; jsdom does not implement them.
  Element.prototype.scrollIntoView = vi.fn()
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.releasePointerCapture = vi.fn()
})

const tags: ItemTags = {
  colors: ['navy', 'white'],
  primary_color: 'navy',
  pattern: 'striped',
  material: 'cotton',
  formality: 'casual',
  fit: 'slim',
  style: ['preppy'],
  season: ['spring'],
}

function renderEditor(initial: ItemTags = tags, primaryColor: string | undefined = 'navy') {
  const seen: TagDraft[] = []
  function Harness() {
    const [draft, setDraft] = useState(draftFromTags(initial))
    return (
      <ItemTagsEditor
        draft={draft}
        primaryColor={primaryColor}
        onChange={(next) => {
          seen.push(next)
          setDraft(next)
        }}
      />
    )
  }
  render(<Harness />, { wrapper: Wrapper })
  return { last: () => seen[seen.length - 1], seen }
}

function pick(label: string, option: string) {
  fireEvent.keyDown(screen.getByLabelText(label), { key: 'Enter' })
  fireEvent.click(screen.getByRole('option', { name: option }))
}

describe('ItemTagsEditor', () => {
  it('shows the current tags in the user language', () => {
    renderEditor()
    expect(screen.getByLabelText('Pattern')).toHaveTextContent('Striped')
    expect(screen.getByLabelText('Material')).toHaveTextContent('Cotton')
    expect(screen.getByLabelText('Formality')).toHaveTextContent('Casual')
    expect(screen.getByLabelText('Fit')).toHaveTextContent('Slim')
    expect(screen.getByLabelText('Secondary color')).toHaveTextContent('White')
  })

  it('changes a single-value tag', () => {
    const { last } = renderEditor()
    pick('Pattern', 'Plaid')
    expect(last().pattern).toBe('plaid')
    expect(screen.getByLabelText('Pattern')).toHaveTextContent('Plaid')
  })

  it('clears a tag with None', () => {
    const { last } = renderEditor()
    pick('Material', 'None')
    expect(last().material).toBeNull()
  })

  it('offers every pattern, and None first', () => {
    renderEditor()
    fireEvent.keyDown(screen.getByLabelText('Pattern'), { key: 'Enter' })
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['None', ...PATTERN_VALUES.map((value) => messages.constants.patterns[value])])
  })

  it('still shows a value the list no longer offers', () => {
    renderEditor({ ...tags, pattern: 'paisley' })
    expect(screen.getByLabelText('Pattern')).toHaveTextContent('Paisley')
  })

  it('switches style chips on and off', () => {
    const { last } = renderEditor()
    const group = screen.getByRole('group', { name: 'Style' })
    const sporty = within(group).getByRole('button', { name: 'Sporty' })
    expect(sporty).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(sporty)
    expect(last().style).toEqual(['preppy', 'sporty'])
    expect(sporty).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(sporty)
    expect(last().style).toEqual(['preppy'])
  })

  it('can switch off a season the list does not offer', () => {
    const { last } = renderEditor({ ...tags, season: ['monsoon'] })
    const group = screen.getByRole('group', { name: 'Season' })
    fireEvent.click(within(group).getByRole('button', { name: 'Monsoon' }))
    expect(last().season).toEqual([])
  })

  it('does not offer the primary colour as a secondary colour', () => {
    renderEditor()
    fireEvent.keyDown(screen.getByLabelText('Secondary color'), { key: 'Enter' })
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options).not.toContain('Navy')
    expect(options).toContain('White')
  })

  it('asks for a tertiary colour only once there is a secondary one', () => {
    const { last } = renderEditor({ ...tags, colors: ['navy'] })
    expect(screen.queryByLabelText('Tertiary color')).not.toBeInTheDocument()

    pick('Secondary color', 'Red')
    expect(last().extraColors).toEqual(['red'])
    expect(screen.getByLabelText('Tertiary color')).toBeInTheDocument()

    pick('Tertiary color', 'Gray')
    expect(last().extraColors).toEqual(['red', 'gray'])
  })

  it('does not offer the secondary colour again as the tertiary one', () => {
    renderEditor({ ...tags, colors: ['navy', 'red'] })
    fireEvent.keyDown(screen.getByLabelText('Tertiary color'), { key: 'Enter' })
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options).not.toContain('Red')
    expect(options).not.toContain('Navy')
  })

  it('moves the tertiary colour up when the secondary one is removed', () => {
    const { last } = renderEditor({ ...tags, colors: ['navy', 'red', 'gray'] })
    pick('Secondary color', 'None')
    expect(last().extraColors).toEqual(['gray'])
    expect(screen.getByLabelText('Secondary color')).toHaveTextContent('Gray')
    expect(screen.queryByLabelText('Tertiary color')).toHaveTextContent('None')
  })

  it('keeps colours beyond the third when the first two change', () => {
    const { last } = renderEditor({ ...tags, colors: ['navy', 'red', 'gray', 'gold'] })
    pick('Secondary color', 'Green')
    expect(last().extraColors).toEqual(['green', 'gray', 'gold'])
  })
})
