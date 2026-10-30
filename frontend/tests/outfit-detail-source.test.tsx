import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { describe, expect, it, vi } from 'vitest'
import OutfitDetailPage from '@/app/dashboard/outfits/[id]/page'

vi.unmock('next-intl')

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useParams: () => ({ id: 'o1' }),
}))

const outfit = vi.hoisted(() => ({
  replaces_outfit_id: null as string | null,
  id: 'o1',
  scheduled_for: '2026-10-05',
  source: 'on_demand',
  occasion: 'casual',
  name: 'Look' as string | null,
  items: [] as Array<Record<string, unknown>>,
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

describe('outfit detail source label', () => {
  it('shows the translated source on the German locale', () => {
    const de = {
      outfits: messages('de', 'outfits'),
      common: messages('de', 'common'),
      history: messages('de', 'history'),
      constants: messages('de', 'constants'),
    }
    render(
      <NextIntlClientProvider locale="de" messages={de} onError={() => {}}>
        <OutfitDetailPage />
      </NextIntlClientProvider>,
    )
    expect(screen.getByText(de.constants.outfitSources.onDemand)).toBeInTheDocument()
    expect(screen.queryByText('on demand')).not.toBeInTheDocument()
  })

  it('shows the translated wore-instead title for an unnamed replacement', () => {
    outfit.name = null
    outfit.replaces_outfit_id = 'o0'
    const de = {
      outfits: messages('de', 'outfits'),
      common: messages('de', 'common'),
      history: messages('de', 'history'),
      constants: messages('de', 'constants'),
    }
    render(
      <NextIntlClientProvider locale="de" messages={de} onError={() => {}}>
        <OutfitDetailPage />
      </NextIntlClientProvider>,
    )
    expect(screen.getByRole('heading', { name: `${de.constants.occasions.casual} (stattdessen getragen)` })).toBeInTheDocument()
    outfit.name = 'Look'
    outfit.replaces_outfit_id = null
  })

  it('links an outfit item to the wardrobe item dialog', () => {
    const en = {
      outfits: messages('en', 'outfits'),
      common: messages('en', 'common'),
      history: messages('en', 'history'),
      constants: messages('en', 'constants'),
    }
    outfit.items = [
      {
        id: 'i1',
        type: 'shirt',
        subtype: null,
        name: 'Shirt',
        primary_color: null,
        colors: [],
        image_path: null,
        thumbnail_path: null,
        image_url: null,
        thumbnail_url: null,
        layer_type: null,
        position: 1,
      },
    ]
    render(
      <NextIntlClientProvider locale="en" messages={en} onError={() => {}}>
        <OutfitDetailPage />
      </NextIntlClientProvider>,
    )
    const link = screen
      .getAllByRole('link')
      .find((element) => element.getAttribute('href')?.startsWith('/dashboard/wardrobe'))
    expect(link).toHaveAttribute('href', '/dashboard/wardrobe?item=i1')
    outfit.items = []
  })
})
