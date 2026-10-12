import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

const post = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ info: vi.fn(), success: vi.fn(), error: vi.fn() }))

vi.mock('@/lib/api', () => ({ api: { post }, getErrorMessage: (_: unknown, fallback: string) => fallback }))
vi.mock('sonner', () => ({ toast }))
// The global next-intl mock drops the namespace and ICU values, so this one keeps both to
// prove the skip toast names the slot through the translated role catalog.
vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => {
    const t = (key: string, values?: Record<string, unknown>) =>
      `${namespace}.${key}${values ? ` ${JSON.stringify(values)}` : ''}`
    t.has = () => true
    return t
  },
}))

import { DetailsPanel } from '@/components/studio/details-panel'

describe('DetailsPanel AI assist', () => {
  it('names the taken slot with its translated role label', async () => {
    post.mockResolvedValue({
      items: [{ id: '2', type: 't-shirt', name: 'Tee', primary_color: 'white' }],
    })
    render(
      <DetailsPanel
        items={[{ id: '1', type: 'shirt', name: 'Shirt', thumbnail_url: null, image_url: null, primary_color: 'blue' }]}
        name=""
        occasion="casual"
        onNameChange={vi.fn()}
        onOccasionChange={vi.fn()}
        onAiMerge={vi.fn()}
      />
    )
    fireEvent.click(screen.getByText('outfits.details.letAiFinish'))
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        'outfits.details.skippedItem {"name":"Tee","slot":"constants.roles.base_top"}'
      )
    )
  })
})
