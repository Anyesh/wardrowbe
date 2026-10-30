import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { ItemDetailDialog } from '@/components/item-detail-dialog'
import { ApiError, api } from '@/lib/api'
import { createQueryClient } from '@/lib/query-client'
import type { Item } from '@/lib/types'

vi.unmock('next-intl')
vi.mock('@/lib/api', async () => ({
  ...(await vi.importActual('@/lib/api')),
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
  // The app's client, so the global error toast is live and a second toast would show.
  const client = createQueryClient()
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
    vi.mocked(toast.error).mockClear()
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

  it('sends no colours on a rename when the primary is only in the colour list', async () => {
    renderDialog({
      primary_color: null,
      colors: ['red', 'blue'],
      tags: { colors: ['red', 'blue'], style: [], season: [] },
    } as unknown as Partial<Item>)
    startEditing()
    fireEvent.change(screen.getByPlaceholderText(labels.placeholders.itemName), {
      target: { value: 'My oxford' },
    })

    const { body } = await save()

    expect(body).toEqual({ name: 'My oxford' })
  })

  it('sends no colours on a rename when the primary column and the tags disagree', async () => {
    renderDialog({
      primary_color: 'navy',
      colors: ['black', 'white'],
      tags: { colors: ['black', 'white'], primary_color: 'black', style: [], season: [] },
    } as unknown as Partial<Item>)
    startEditing()
    fireEvent.change(screen.getByPlaceholderText(labels.placeholders.itemName), {
      target: { value: 'My oxford' },
    })

    const { body } = await save()

    expect(body).toEqual({ name: 'My oxford' })
  })

  it('sends a new primary colour on its own, without a colour list', async () => {
    renderDialog({
      colors: ['navy', 'white'],
      tags: { ...item.tags, colors: ['navy', 'white'] },
    } as unknown as Partial<Item>)
    startEditing()
    const primary = screen.getAllByRole('combobox').find((el) => el.textContent?.includes('Navy'))!
    fireEvent.keyDown(primary, { key: 'Enter' })
    fireEvent.click(screen.getByRole('option', { name: 'Red' }))

    const { body } = await save()

    expect(body).toEqual({ primary_color: 'red' })
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

    fireEvent.change(screen.getByPlaceholderText(labels.placeholders.itemName), {
      target: { value: 'My oxford' },
    })
    const { body } = await save()
    expect(body).not.toHaveProperty('tags')
  })

  it('saves nothing when nothing was changed', async () => {
    renderDialog()
    startEditing()

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(screen.queryByText(labels.tagsEditor.title)).not.toBeInTheDocument())
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('sends only the fields that were changed', async () => {
    renderDialog()
    startEditing()
    fireEvent.change(screen.getByPlaceholderText(labels.placeholders.itemName), {
      target: { value: 'My oxford' },
    })

    const { body } = await save()

    expect(body).toEqual({ name: 'My oxford' })
  })

  it('keeps tags and colours the AI added while the form was open', async () => {
    // The form opens on an item still being analysed; tagging finishes before the person saves
    // an unrelated change. Nothing the AI just wrote may be sent back as a clear or an edit.
    const bare = {
      ...item,
      type: 'unknown',
      subtype: null,
      primary_color: null,
      colors: [],
      tags: { colors: [], style: [], season: [] },
    } as unknown as Item
    const { rerender } = render(<ItemDetailDialog item={bare} open onOpenChange={() => {}} />, {
      wrapper: Wrapper,
    })
    startEditing()
    rerender(<ItemDetailDialog item={item} open onOpenChange={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText(labels.placeholders.itemName), {
      target: { value: 'My oxford' },
    })

    const { body } = await save()

    expect(body).toEqual({ name: 'My oxford' })
  })

  it('keeps the type the AI could not place as the subtype when a type is picked', async () => {
    renderDialog({ type: 'unknown', subtype: null, ai_unrecognized_type: 'culottes' } as Partial<Item>)
    startEditing()
    fireEvent.keyDown(screen.getAllByRole('combobox')[0], { key: 'Enter' })
    fireEvent.click(screen.getByRole('option', { name: 'Shorts' }))

    const { body } = await save()

    expect(body.type).toBe('shorts')
    expect(body.subtype).toBe('culottes')
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

  it.each([
    [
      'a value off the list',
      422,
      { detail: { message: 'x', error_code: 'INVALID_TAG_VALUE' } },
      labels.tagsEditor.invalidValue,
    ],
    ['any other failure', 500, { detail: 'Internal Server Error' }, labels.actions.saveError],
  ])('shows one translated toast when a save fails with %s', async (_case, status, data, message) => {
    vi.mocked(api.patch).mockRejectedValue(new ApiError('raw server text', status, data))
    renderDialog()
    startEditing()
    fireEvent.change(screen.getByPlaceholderText(labels.placeholders.itemName), {
      target: { value: 'My oxford' },
    })

    await save()

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(toast.error).toHaveBeenCalledTimes(1)
    expect(toast.error).toHaveBeenCalledWith(message)
  })

  it('shows one translated toast when the favourite toggle fails', async () => {
    vi.mocked(api.patch).mockRejectedValue(new ApiError('raw server text', 500, {}))
    renderDialog()

    fireEvent.click(screen.getByTitle(labels.titles.toggleFavorite))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(toast.error).toHaveBeenCalledTimes(1)
    expect(toast.error).toHaveBeenCalledWith(labels.actions.saveError)
  })
})
