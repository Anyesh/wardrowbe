import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ExportDialog } from '@/components/export-dialog'
import { ApiError, api } from '@/lib/api'
import type { BulkOperationParams } from '@/lib/hooks/use-items'

vi.unmock('next-intl')
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { postForText: vi.fn() },
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const catalog = (namespace: string) =>
  JSON.parse(readFileSync(resolve(__dirname, '..', 'messages', 'en', `${namespace}.json`), 'utf8'))
const messages = { wardrobe: catalog('wardrobe'), errors: catalog('errors') }

function renderDialog(selection: BulkOperationParams | null = null, selectedCount = 0) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ExportDialog
        open
        onOpenChange={() => {}}
        totalCount={40}
        selection={selection}
        selectedCount={selectedCount}
      />
    </NextIntlClientProvider>,
  )
}

const postForText = vi.mocked(api.postForText)

describe('ExportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    postForText.mockResolvedValue('---\nname: wardrobe-stylist\n---\n')
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
  })

  it('exports the whole wardrobe as a skill by default', async () => {
    renderDialog()

    expect(screen.queryByText(/selected item/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalled())
    expect(postForText).toHaveBeenCalledWith('/items/export', {
      format: 'skill',
      include_profile: true,
    })
  })

  it('sends the explicit selection, and the whole wardrobe once the user switches', async () => {
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

    fireEvent.click(screen.getByRole('button', { name: 'Whole wardrobe (40)' }))
    // The copy button reads "Copied to clipboard" for a moment after the first copy.
    await waitFor(() => expect(screen.getByRole('button', { name: /^Cop/ })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: /^Cop/ }))
    await waitFor(() =>
      expect(postForText).toHaveBeenLastCalledWith('/items/export', {
        format: 'json',
        include_profile: false,
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
