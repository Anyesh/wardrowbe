import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { ItemDetailDialog } from '@/components/item-detail-dialog'
import { api } from '@/lib/api'
import type { Item } from '@/lib/types'

vi.unmock('next-intl')
vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

function catalog(namespace: string) {
  return JSON.parse(readFileSync(resolve(__dirname, '..', 'messages', 'en', `${namespace}.json`), 'utf8'))
}
const wardrobe = catalog('wardrobe')
const labels = wardrobe.itemDetail

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const all = Object.fromEntries(['wardrobe', 'constants', 'common'].map((ns) => [ns, catalog(ns)]))
  return (
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="en" messages={all} onError={() => {}}>
        {children}
      </NextIntlClientProvider>
    </QueryClientProvider>
  )
}

beforeAll(() => {
  // Radix Select calls these on open; jsdom does not implement them.
  Element.prototype.scrollIntoView = vi.fn()
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.releasePointerCapture = vi.fn()
})

const item = {
  id: 'i1',
  type: 'shirt',
  subtype: 'oxford',
  name: 'Oxford',
  status: 'ready',
  favorite: false,
  primary_color: 'navy',
  colors: ['navy'],
  tags: {
    colors: ['navy'],
    primary_color: 'navy',
    pattern: 'striped',
    style: ['preppy'],
    season: ['spring'],
    size: 'M',
    logprobs_confidence: 0.66,
  },
  images: [],
  image_url: 'https://example.test/i1.jpg?x=1',
  thumbnail_url: 'https://example.test/i1-thumb.jpg',
  wear_count: 0,
  wears_since_wash: 0,
  effective_wash_interval: 3,
} as unknown as Item

function renderDialog(overrides: Partial<Item> = {}) {
  render(<ItemDetailDialog item={{ ...item, ...overrides } as Item} open onOpenChange={() => {}} />, {
    wrapper: Wrapper,
  })
}

function startEditing() {
  fireEvent.click(screen.getByTitle(labels.actions.editItem))
}

async function save() {
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1))
  const [path, body] = vi.mocked(api.patch).mock.calls[0]
  return { path, body: body as Record<string, unknown> }
}

describe('editing an item with the tag editor', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(api.patch).mockReset()
    vi.mocked(api.patch).mockResolvedValue(item)
  })

  it('shows the tag editor in edit mode', () => {
    renderDialog()
    expect(screen.queryByText(labels.tagsEditor.title)).not.toBeInTheDocument()
    startEditing()
    expect(screen.getByText(labels.tagsEditor.title)).toBeInTheDocument()
    expect(screen.getByLabelText(labels.tagsEditor.pattern)).toHaveTextContent('Striped')
  })

  it('sends no tags when only a plain field was edited', async () => {
    // A null or empty tags object used to wipe every tag on the server.
    renderDialog()
    startEditing()
    fireEvent.change(screen.getByPlaceholderText(labels.placeholders.itemName), {
      target: { value: 'My oxford' },
    })

    const { path, body } = await save()

    expect(path).toBe('/items/i1')
    expect(body.name).toBe('My oxford')
    expect(body).not.toHaveProperty('tags')
  })

  it('sends only the tags that were changed', async () => {
    renderDialog()
    startEditing()
    const style = screen.getByRole('group', { name: labels.tagsEditor.style })
    fireEvent.click(within(style).getByRole('button', { name: 'Sporty' }))
    fireEvent.keyDown(screen.getByLabelText(labels.tagsEditor.pattern), { key: 'Enter' })
    fireEvent.click(screen.getByRole('option', { name: 'Plaid' }))

    const { body } = await save()

    expect(body.tags).toEqual({ pattern: 'plaid', style: ['preppy', 'sporty'] })
  })

  it('clears a tag with null', async () => {
    renderDialog()
    startEditing()
    fireEvent.keyDown(screen.getByLabelText(labels.tagsEditor.pattern), { key: 'Enter' })
    fireEvent.click(screen.getByRole('option', { name: labels.tagsEditor.none }))

    const { body } = await save()

    expect(body.tags).toEqual({ pattern: null })
  })

  it('adds a secondary colour after the primary one', async () => {
    renderDialog()
    startEditing()
    fireEvent.keyDown(screen.getByLabelText(labels.tagsEditor.secondaryColor), { key: 'Enter' })
    fireEvent.click(screen.getByRole('option', { name: 'White' }))

    const { body } = await save()

    expect(body.tags).toEqual({ colors: ['navy', 'white'] })
  })

  it('forgets tag changes that were cancelled', async () => {
    renderDialog()
    startEditing()
    const style = screen.getByRole('group', { name: labels.tagsEditor.style })
    fireEvent.click(within(style).getByRole('button', { name: 'Sporty' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    startEditing()
    expect(
      within(screen.getByRole('group', { name: labels.tagsEditor.style })).getByRole('button', {
        name: 'Sporty',
      }),
    ).toHaveAttribute('aria-pressed', 'false')

    const { body } = await save()
    expect(body).not.toHaveProperty('tags')
  })

  it('does not send a type or subtype that did not change as an edit', async () => {
    renderDialog()
    startEditing()

    const { body } = await save()

    expect(body.type).toBe('shirt')
    expect(body.subtype).toBe('oxford')
    expect(body).not.toHaveProperty('tags')
  })

  it('drops a subtype that belongs to the old type when the type changes', async () => {
    renderDialog({ type: 't-shirt', subtype: 'button-down' })
    startEditing()
    const typeSelect = screen.getAllByRole('combobox')[0]
    fireEvent.keyDown(typeSelect, { key: 'Enter' })
    fireEvent.click(screen.getByRole('option', { name: 'Polo' }))

    expect(screen.getByPlaceholderText(labels.placeholders.subtype)).toHaveValue('')
    const { body } = await save()
    expect(body.type).toBe('polo')
    expect(body.subtype).toBeNull()
  })

  it('keeps a subtype that fits the new type', async () => {
    renderDialog({ type: 't-shirt', subtype: 'button-down' })
    startEditing()
    fireEvent.keyDown(screen.getAllByRole('combobox')[0], { key: 'Enter' })
    fireEvent.click(screen.getByRole('option', { name: 'Shirt' }))

    expect(screen.getByPlaceholderText(labels.placeholders.subtype)).toHaveValue('button-down')
  })
})
