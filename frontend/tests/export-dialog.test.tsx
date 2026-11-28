import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ExportDialog } from '@/components/export-dialog'
import { ApiError, api } from '@/lib/api'
import type { BulkItemFilters, BulkOperationParams } from '@/lib/hooks/use-items'

vi.unmock('next-intl')
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { postForText: vi.fn(), post: vi.fn() },
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const catalog = (namespace: string) =>
  JSON.parse(readFileSync(resolve(__dirname, '..', 'messages', 'en', `${namespace}.json`), 'utf8'))
const messages = {
  wardrobe: catalog('wardrobe'),
  errors: catalog('errors'),
  constants: catalog('constants'),
}

function renderDialog(
  selection: BulkOperationParams | null = null,
  selectedCount = 0,
  viewFilters: BulkItemFilters = {},
) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ExportDialog
        open
        onOpenChange={() => {}}
        viewFilters={viewFilters}
        totalCount={40}
        selection={selection}
        selectedCount={selectedCount}
      />
    </NextIntlClientProvider>,
  )
}

function readBlob(blob: Blob) {
  return new Promise<string>((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.readAsText(blob)
  })
}

const postForText = vi.mocked(api.postForText)
const post = vi.mocked(api.post)

const jsonExport = {
  exported_at: '2026-11-28T12:00:00+00:00',
  item_count: 2,
  items: [
    { section: 'tops', type: 'shirt', name: 'Linen shirt', primary_color: 'navy', colors: [], style: [], season: [], description: 'Loose fit.' },
    { section: 'footwear', type: 'sneakers', name: null, primary_color: null, colors: [], style: [], season: [], description: null },
  ],
}

describe('ExportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    postForText.mockResolvedValue('---\nname: wardrobe-stylist\n---\n')
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
  })

  it('exports everything the page shows as a skill by default', async () => {
    renderDialog(null, 0, { type: 'shirt' })

    expect(screen.queryByText(/selected item/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalled())
    expect(postForText).toHaveBeenCalledWith('/items/export', {
      format: 'skill',
      include_profile: true,
      filters: { type: 'shirt' },
    })
  })

  it('sends the explicit selection, and everything shown once the user switches', async () => {
    renderDialog({ item_ids: ['a', 'b'] }, 2)

    fireEvent.click(screen.getByRole('button', { name: /JSON data/ }))
    fireEvent.click(screen.getByLabelText('Include my style preferences and sizes'))
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
    await waitFor(() =>
      expect(postForText).toHaveBeenLastCalledWith('/items/export', {
        format: 'json',
        include_profile: false,
        item_ids: ['a', 'b'],
      }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Everything shown (40)' }))
    // The copy button reads "Copied to clipboard" for a moment after the first copy.
    await waitFor(() => expect(screen.getByRole('button', { name: /^Cop/ })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: /^Cop/ }))
    await waitFor(() =>
      expect(postForText).toHaveBeenLastCalledWith('/items/export', {
        format: 'json',
        include_profile: false,
        filters: {},
      }),
    )
  })

  it('turns a select-all into the same filters and exclusions', async () => {
    renderDialog(
      { select_all: true, filters: { type: 'shirt' }, excluded_ids: ['x'] },
      12,
    )

    expect(screen.getByRole('button', { name: '12 selected items' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))

    await waitFor(() =>
      expect(postForText).toHaveBeenCalledWith('/items/export', {
        format: 'skill',
        include_profile: true,
        filters: { type: 'shirt' },
        excluded_ids: ['x'],
      }),
    )
  })

  it('renders the Markdown catalogue from the JSON export and downloads it', async () => {
    post.mockResolvedValue(jsonExport)
    const createObjectURL = vi.fn((_blob: Blob) => 'blob:export')
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    renderDialog(null, 0, { type: 'shirt' })

    fireEvent.click(screen.getByRole('button', { name: /Markdown catalog/ }))
    expect(screen.queryByLabelText('Include my style preferences and sizes')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Download' }))

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Downloaded wardrobe.md'))
    expect(postForText).not.toHaveBeenCalled()
    expect(post).toHaveBeenCalledWith('/items/export', {
      format: 'json',
      include_profile: false,
      filters: { type: 'shirt' },
    })
    const file = await readBlob(createObjectURL.mock.calls[0][0])
    expect(file).toContain('# Wardrobe\n')
    expect(file).toContain('## Tops (1)\n- **[1] "Linen shirt" - Shirt**')
    expect(file).toContain('  - Description: Loose fit.')
    expect(file).toContain('## Footwear (1)\n- **[2] Sneakers**')
  })

  it('copies plain text as one line per item', async () => {
    post.mockResolvedValue(jsonExport)
    renderDialog()

    fireEvent.click(screen.getByRole('button', { name: /Plain text/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        '1. "Linen shirt" - Shirt [Navy]: Loose fit.\n2. Sneakers\n',
      ),
    )
  })

  it('shows the translated message for a coded error', async () => {
    postForText.mockRejectedValue(
      new ApiError('English detail', 400, {
        detail: 'English detail',
        error_code: 'EXPORT_TOO_LARGE',
        params: { limit: 2000 },
      }),
    )
    renderDialog()

    fireEvent.click(screen.getByRole('button', { name: 'Download' }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('You can export up to 2000 items at a time.'),
    )
  })
})
