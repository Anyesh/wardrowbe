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
  id: 'o1',
  scheduled_for: '2026-10-05',
  source: 'on_demand',
  occasion: 'casual',
  name: 'Look',
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
vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useOccasionLabel: () => (v: string) => v,
  useTypeLabel: () => (v: string) => v,
}))
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
    }
    render(
      <NextIntlClientProvider locale="de" messages={de} onError={() => {}}>
        <OutfitDetailPage />
      </NextIntlClientProvider>,
    )
    expect(screen.getByText(de.history.sourceBadges.onDemand)).toBeInTheDocument()
    expect(screen.queryByText('on demand')).not.toBeInTheDocument()
  })
})
