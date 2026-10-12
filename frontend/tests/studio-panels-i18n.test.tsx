import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const post = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ info: vi.fn(), success: vi.fn(), error: vi.fn() }))

vi.mock('@/lib/api', () => ({ api: { post }, getErrorMessage: (_: unknown, fallback: string) => fallback }))
vi.mock('sonner', () => ({ toast }))
// The global next-intl mock drops the namespace and ICU values, so this one keeps both to
// prove each label comes from the catalogs rather than from raw values.
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

import { CanvasPanel } from '@/components/studio/canvas-panel'
import { DetailsPanel } from '@/components/studio/details-panel'
import type { StudioItem } from '@/lib/studio/editor-state'

function studioItem(id: string, type: string, name: string | null = null): StudioItem {
  return { id, type, name, thumbnail_url: null, image_url: null, primary_color: 'blue' }
}

function assistWith(canvas: StudioItem[], suggested: StudioItem[]) {
  post.mockResolvedValue({ items: suggested })
  render(
    <DetailsPanel
      items={canvas}
      name=""
      occasion="casual"
      onNameChange={vi.fn()}
      onOccasionChange={vi.fn()}
      onAiMerge={vi.fn()}
    />
  )
  fireEvent.click(screen.getByText('outfits.details.letAiFinish'))
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DetailsPanel AI assist', () => {
  it('names the canvas piece that already fills the spot', async () => {
    assistWith([studioItem('1', 'shirt', 'Shirt')], [studioItem('2', 't-shirt', 'Tee')])
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        'outfits.details.skippedItem {"name":"Tee","other":"Shirt"}'
      )
    )
  })

  it('falls back to translated type labels for unnamed pieces', async () => {
    assistWith([studioItem('1', 'dress')], [studioItem('2', 'shirt')])
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        'outfits.details.skippedItem {"name":"constants.types.shirt","other":"constants.types.dress"}'
      )
    )
  })
})

describe('CanvasPanel', () => {
  it('labels a type without a role through the type catalog', () => {
    render(<CanvasPanel items={[studioItem('1', 'kimono', 'Kimono')]} onRemove={vi.fn()} />)
    expect(screen.getAllByText('constants.types.kimono').length).toBeGreaterThan(0)
    expect(screen.queryByText('kimono')).toBeNull()
  })
})
