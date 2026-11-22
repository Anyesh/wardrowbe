import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ info: vi.fn(), success: vi.fn(), error: vi.fn() }))
const aiUi = vi.hoisted(() => ({ enabled: true }))

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { post },
}))
vi.mock('sonner', () => ({ toast }))
vi.mock('@/lib/hooks/use-features', () => ({ useAiUiEnabled: () => aiUi.enabled }))
vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useFormatter: () => ({
    number: (value: number) => String(value),
    list: (items: string[]) => items.join(', '),
  }),
  useTranslations: (namespace: string) => {
    const t = (key: string, values?: Record<string, unknown>) =>
      `${namespace}.${key}${values ? ` ${JSON.stringify(values)}` : ''}`
    t.raw = t
    t.rich = t
    t.markup = t
    t.has = () => true
    return t
  },
}))

import { DetailsPanel } from '@/components/studio/details-panel'
import type { StudioItem } from '@/lib/studio/editor-state'
import {
  applySuggestion,
  canApplySuggestion,
  type OutfitCheckItem,
  type OutfitCheckResult,
  type OutfitCheckSuggestion,
} from '@/lib/studio/outfit-check'

function item(id: string, type: string, name: string | null = null): StudioItem {
  return { id, type, name, thumbnail_url: null, image_url: null, primary_color: 'blue' }
}

function wardrobeItem(id: string, type: string, name: string): OutfitCheckItem {
  return { id, type, name, primary_color: null, image_url: null, thumbnail_url: null }
}

function suggestion(overrides: Partial<OutfitCheckSuggestion>): OutfitCheckSuggestion {
  return {
    action: 'styling_tip',
    title: 'Tip',
    description: '',
    reason: '',
    target_item_id: null,
    replacement_item: null,
    ...overrides,
  }
}

const tee = item('tee', 't-shirt', 'Grey tee')
const jeans = item('jeans', 'jeans', 'Blue jeans')
const sneakers = item('sneakers', 'sneakers', 'White sneakers')

describe('applySuggestion', () => {
  it('swaps the target for the replacement and keeps canonical order', () => {
    const next = applySuggestion(
      [jeans, tee],
      suggestion({
        action: 'replace',
        target_item_id: 'tee',
        replacement_item: wardrobeItem('oxford', 'shirt', 'Oxford'),
      }),
    )
    expect(next.map((i) => i.id)).toEqual(['oxford', 'jeans'])
  })

  it('lets a full-body piece displace the top and bottom it covers', () => {
    const next = applySuggestion(
      [tee, jeans, sneakers],
      suggestion({ action: 'add', replacement_item: wardrobeItem('dress', 'dress', 'Dress') }),
    )
    expect(next.map((i) => i.id)).toEqual(['dress', 'sneakers'])
  })

  it('adds an accessory alongside everything else', () => {
    const next = applySuggestion(
      [tee, jeans],
      suggestion({ action: 'add', replacement_item: wardrobeItem('belt', 'belt', 'Belt') }),
    )
    expect(next.map((i) => i.id).sort()).toEqual(['belt', 'jeans', 'tee'])
  })

  it('removes the target', () => {
    const next = applySuggestion(
      [tee, jeans, sneakers],
      suggestion({ action: 'remove', target_item_id: 'sneakers' }),
    )
    expect(next.map((i) => i.id)).toEqual(['tee', 'jeans'])
  })

  it('leaves the canvas alone once a suggestion no longer applies', () => {
    const canvas = [tee, jeans]
    const add = suggestion({ action: 'add', replacement_item: wardrobeItem('tee', 't-shirt', 'Tee') })
    const remove = suggestion({ action: 'remove', target_item_id: 'gone' })
    const tip = suggestion({ action: 'styling_tip' })
    for (const s of [add, remove, tip]) {
      expect(canApplySuggestion(canvas, s)).toBe(false)
      expect(applySuggestion(canvas, s)).toBe(canvas)
    }
  })
})

const review: OutfitCheckResult = {
  rating: 6,
  verdict: 'Too casual',
  opinion: 'The rooftop is dressier than this.',
  strengths: ['Good fit'],
  improvements: ['Needs a sharper top'],
  suggestions: [
    suggestion({
      action: 'replace',
      title: 'Sharper top',
      target_item_id: 'tee',
      replacement_item: wardrobeItem('oxford', 'shirt', 'Oxford shirt'),
    }),
  ],
}

function renderPanel(canvas: StudioItem[] = [tee, jeans], occasion: string | null = 'date') {
  const onAiMerge = vi.fn()
  render(
    <DetailsPanel
      items={canvas}
      name=""
      occasion={occasion}
      onNameChange={vi.fn()}
      onOccasionChange={vi.fn()}
      onAiMerge={onAiMerge}
    />,
  )
  return { onAiMerge }
}

describe('DetailsPanel outfit check', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    aiUi.enabled = true
  })

  it('stays disabled until there is a destination and an occasion', () => {
    renderPanel([tee], null)
    const button = screen.getByRole('button', { name: 'outfits.details.checkOutfit' })
    fireEvent.change(screen.getByLabelText('outfits.details.destination'), {
      target: { value: 'Rooftop dinner' },
    })
    expect(button).toBeDisabled()
  })

  it('sends the outfit and shows the review, whose swap updates the canvas', async () => {
    post.mockResolvedValue(review)
    const { onAiMerge } = renderPanel()

    fireEvent.change(screen.getByLabelText('outfits.details.destination'), {
      target: { value: '  Rooftop dinner ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'outfits.details.checkOutfit' }))

    await screen.findByText('The rooftop is dressier than this.')
    expect(post).toHaveBeenCalledWith('/outfits/check', {
      items: ['tee', 'jeans'],
      destination: 'Rooftop dinner',
      occasion: 'date',
    })
    expect(screen.getByText('Grey tee → Oxford shirt')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'outfits.review.apply.replace' }))
    expect(onAiMerge).toHaveBeenCalledWith([
      expect.objectContaining({ id: 'oxford' }),
      expect.objectContaining({ id: 'jeans' }),
    ])
  })

  it('shows a translated toast when the check fails', async () => {
    post.mockRejectedValue(new Error('boom'))
    renderPanel()

    fireEvent.change(screen.getByLabelText('outfits.details.destination'), {
      target: { value: 'Office' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'outfits.details.checkOutfit' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(screen.queryByText('outfits.review.title')).toBeNull()
  })

  it('is hidden when the AI UI is turned off', () => {
    aiUi.enabled = false
    renderPanel()
    expect(screen.queryByLabelText('outfits.details.destination')).toBeNull()
  })
})
