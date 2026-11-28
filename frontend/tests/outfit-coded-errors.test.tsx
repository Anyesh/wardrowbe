import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CloneToLookbookDialog } from '@/components/shared/clone-to-lookbook-dialog'
import { GeneratePairingsDialog } from '@/components/generate-pairings-dialog'
import { ApiError, api } from '@/lib/api'
import { isWornImmutableError } from '@/lib/studio/errors'
import type { Item } from '@/lib/types'

vi.unmock('next-intl')
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const catalog = (locale: string, namespace: string) =>
  JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', locale, `${namespace}.json`), 'utf8'),
  )
const messages = Object.fromEntries(
  ['common', 'constants', 'outfits', 'pairings', 'errors'].map((ns) => [ns, catalog('en', ns)]),
)

function renderWithIntl(ui: React.ReactElement) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
      <NextIntlClientProvider locale="en" messages={messages}>
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>,
  )
}

const coded = (status: number, code: string) =>
  new ApiError('English detail', status, { detail: 'English detail', error_code: code })

describe('isWornImmutableError', () => {
  it('matches the top-level error code', () => {
    expect(isWornImmutableError(coded(409, 'OUTFIT_WORN_IMMUTABLE'))).toBe(true)
  })

  it('ignores other codes, uncoded errors and non-API errors', () => {
    expect(isWornImmutableError(coded(409, 'SOURCE_BUSY'))).toBe(false)
    expect(isWornImmutableError(new ApiError('x', 409, { detail: 'x' }))).toBe(false)
    expect(isWornImmutableError(new Error('x'))).toBe(false)
  })
})

describe('outfit dialogs translate API errors by code', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the translated message when the clone fails with a code', async () => {
    vi.mocked(api.post).mockRejectedValue(coded(404, 'OUTFIT_NOT_FOUND'))
    renderWithIntl(
      <CloneToLookbookDialog open sourceOutfitId="o1" sourceOccasion="casual" onClose={() => {}} />,
    )

    fireEvent.click(screen.getByRole('button', { name: messages.common.save }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1))
    expect(toast.error).toHaveBeenCalledWith(messages.errors.OUTFIT_NOT_FOUND)
  })

  it('shows the local fallback when the failure has no code', async () => {
    vi.mocked(api.post).mockRejectedValue(new ApiError('Internal Server Error', 500, {}))
    renderWithIntl(
      <CloneToLookbookDialog open sourceOutfitId="o1" sourceOccasion="casual" onClose={() => {}} />,
    )

    fireEvent.click(screen.getByRole('button', { name: messages.common.save }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1))
    expect(toast.error).toHaveBeenCalledWith(messages.outfits.cloneToLookbook.saveError)
  })

  it('translates a pairing failure instead of showing the English detail', async () => {
    vi.mocked(api.post).mockRejectedValue(coded(400, 'INSUFFICIENT_ITEMS_FOR_PAIRING'))
    const item = { id: 'i1', type: 'shirt', tags: {}, images: [] } as unknown as Item
    renderWithIntl(<GeneratePairingsDialog item={item} open onOpenChange={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: new RegExp(messages.pairings.generate.generate) }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1))
    expect(toast.error).toHaveBeenCalledWith(messages.errors.INSUFFICIENT_ITEMS_FOR_PAIRING)
  })
})
