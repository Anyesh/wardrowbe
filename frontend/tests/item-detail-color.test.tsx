import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { describe, expect, it, vi } from 'vitest'
import type { Item } from '@/lib/types'
import { ItemDetailDialog } from '@/components/item-detail-dialog'

vi.unmock('next-intl')

const { updateItem } = vi.hoisted(() => ({ updateItem: vi.fn().mockResolvedValue({}) }))

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => <img src={src} alt={alt} />,
}))
vi.mock('@/components/color-eyedropper', () => ({ ColorEyedropper: () => null }))
vi.mock('@/components/generate-pairings-dialog', () => ({ GeneratePairingsDialog: () => null }))
vi.mock('@/lib/hooks/use-features', () => ({ useFeatures: () => ({ data: null }) }))
vi.mock('@/lib/hooks/use-items', () => {
  const mutation = () => ({ mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false })
  return {
    useUpdateItem: () => ({ ...mutation(), mutateAsync: updateItem }),
    useDeleteItem: mutation,
    useReanalyzeItem: mutation,
    useRotateImage: mutation,
    useRemoveBackground: mutation,
    useRestoreOriginal: mutation,
    useReplaceItemImage: mutation,
    useLogWash: mutation,
    useAddItemImage: mutation,
    useDeleteItemImage: mutation,
    useSetPrimaryImage: mutation,
    useWashHistory: () => ({ data: null }),
    useItemWearStats: () => ({ data: null }),
    useItemWearHistory: () => ({ data: null }),
  }
})

const messages = Object.fromEntries(['common', 'constants', 'wardrobe'].map((namespace) => [
  namespace,
  JSON.parse(readFileSync(resolve(__dirname, '..', 'messages', 'en', `${namespace}.json`), 'utf8')),
]))

function item(primaryColor: string): Item {
  return {
    id: 'test-item', user_id: 'test-user', type: 'shirt', name: 'Test shirt',
    image_path: '/test-shirt.jpg', image_url: '/test-shirt.jpg',
    tags: { colors: [], style: [], season: [] }, colors: [], primary_color: primaryColor,
    favorite: false, status: 'ready', ai_processed: true, tagging_status: 'tagged',
    wear_count: 0, suggestion_count: 0, acceptance_count: 0, wears_since_wash: 0,
    needs_wash: false, effective_wash_interval: 3, additional_images: [],
    is_archived: false, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  }
}

function renderEditor(primaryColor: string) {
  updateItem.mockClear()
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ItemDetailDialog item={item(primaryColor)} open onOpenChange={vi.fn()} />
    </NextIntlClientProvider>,
  )
  fireEvent.click(screen.getByTitle('Edit item'))
}

describe('item color editor', () => {
  it('shows a mixed-case preset with its swatch and preserves the raw value on save', () => {
    renderEditor('NAVY')

    const colorPicker = screen.getByRole('combobox', { name: 'Primary Color' })
    expect(colorPicker).toHaveTextContent('Navy')
    expect(colorPicker.querySelector('[style*="background-color"]')).toHaveStyle({ backgroundColor: '#1B2A4A' })

    fireEvent.change(screen.getByPlaceholderText('Item name'), { target: { value: 'Updated shirt' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(updateItem).toHaveBeenCalledWith(expect.objectContaining({
      id: 'test-item', data: expect.objectContaining({ name: 'Updated shirt', primary_color: 'NAVY' }),
    }))
  })

  it('shows an out-of-palette value and preserves it on save', () => {
    renderEditor('light-blue')

    const colorPicker = screen.getByRole('combobox', { name: 'Primary Color' })
    expect(colorPicker).toHaveTextContent('Light blue')
    expect(colorPicker.querySelector('[style*="background-color"]')).toBeNull()

    fireEvent.change(screen.getByPlaceholderText('Item name'), { target: { value: 'Updated shirt' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(updateItem).toHaveBeenCalledWith(expect.objectContaining({
      id: 'test-item', data: expect.objectContaining({ name: 'Updated shirt', primary_color: 'light-blue' }),
    }))
  })
})
