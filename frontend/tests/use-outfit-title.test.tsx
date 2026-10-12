import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { describe, expect, it, vi } from 'vitest'
import { OutfitCard } from '@/components/outfits/outfit-card'
import OutfitDetailPage from '@/app/dashboard/outfits/[id]/page'

vi.unmock('next-intl')

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useParams: () => ({ id: 'o1' }),
}))

const outfit = vi.hoisted(() => ({
  id: 'o1',
  scheduled_for: '2026-10-05',
  source: 'on_demand',
  occasion: 'casual',
  name: null as string | null,
  replaces_outfit_id: null as string | null,
  reasoning: null as string | null,
  highlights: [] as string[],
  items: [],
  feedback: null,
}))

vi.mock('@/lib/hooks/use-outfits', () => ({
  useOutfit: () => ({ data: outfit, isLoading: false }),
  useOutfits: () => ({ data: undefined }),
  useDeleteOutfit: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('@/lib/hooks/use-studio', () => ({
  useWearToday: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('@/lib/hooks/use-user', () => ({ useUserToday: () => () => '2026-10-05' }))
vi.mock('@/components/shared/lineage-card', () => ({ LineageCard: () => null }))
vi.mock('@/components/shared/clone-to-lookbook-dialog', () => ({
  CloneToLookbookDialog: () => null,
}))

function messages(locale: string, namespace: string) {
  return JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', locale, `${namespace}.json`), 'utf8'),
  )
}

const de = {
  outfits: messages('de', 'outfits'),
  common: messages('de', 'common'),
  history: messages('de', 'history'),
  constants: messages('de', 'constants'),
}

function wrap(node: React.ReactNode) {
  return (
    <NextIntlClientProvider locale="de" messages={de} onError={() => {}}>
      {node}
    </NextIntlClientProvider>
  )
}

function cardTitle() {
  const { container, unmount } = render(wrap(<OutfitCard outfit={outfit as never} />))
  const text = container.querySelector('h3')?.textContent
  unmount()
  return text
}

function pageTitle() {
  const { unmount } = render(wrap(<OutfitDetailPage />))
  const text = screen.getByRole('heading', { level: 1 }).textContent
  unmount()
  return text
}

describe('outfit title', () => {
  it('uses the translated occasion in the wore-instead fallback', () => {
    outfit.replaces_outfit_id = 'o0'
    const expected = `${de.constants.occasions.casual} (stattdessen getragen)`
    expect(cardTitle()).toBe(expected)
    expect(pageTitle()).toBe(expected)
    outfit.replaces_outfit_id = null
  })

  it('gives the card and the detail page the same title when only highlights exist', () => {
    outfit.highlights = ['Gute Farbkombination']
    expect(cardTitle()).toBe('Gute Farbkombination')
    expect(pageTitle()).toBe('Gute Farbkombination')
    outfit.highlights = []
  })

  it('falls back to the translated occasion outfit title', () => {
    const expected = `${de.constants.occasions.casual}-Outfit`
    expect(cardTitle()).toBe(expected)
    expect(pageTitle()).toBe(expected)
  })
})
