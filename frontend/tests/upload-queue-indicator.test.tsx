import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { DrainState, TerminalRecord } from '@/lib/upload-manager'

const manager = vi.hoisted(() => ({
  init: vi.fn(),
  startDrain: vi.fn(),
  subscribe: vi.fn(() => () => {}),
  getState: vi.fn(),
  retry: vi.fn(),
  retryAll: vi.fn(),
  dismiss: vi.fn(),
  dismissAll: vi.fn(),
  cancelAll: vi.fn(),
}))

vi.mock('@/lib/upload-manager', () => manager)
vi.mock('@/lib/upload-queue', () => ({ getPendingUploads: vi.fn(async () => []) }))
vi.mock('@/lib/hooks/use-features', () => ({
  useFeatures: () => ({ data: { background_removal: false, max_upload_size_mb: 20 } }),
}))

// The global next-intl mock drops ICU values, so this one renders them to prove
// each message receives the file name and the limit.
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key} ${JSON.stringify(values)}` : key,
}))

import { UploadQueueIndicator } from '@/components/upload-queue-indicator'

const MB = 1024 * 1024

function failure(overrides: Partial<TerminalRecord>): TerminalRecord {
  return {
    id: overrides.filename ?? 'id',
    filename: 'photo.jpg',
    size: MB,
    lastError: 'server english',
    errorCode: null,
    retryable: true,
    ...overrides,
  }
}

function renderWith(terminalRecords: TerminalRecord[]) {
  const state: DrainState = {
    draining: false,
    remaining: 0,
    terminalRecords,
    storagePersisted: true,
  }
  manager.getState.mockResolvedValue(state)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <UploadQueueIndicator />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('UploadQueueIndicator failures', () => {
  it('names each failed file with a translated reason instead of the server text', async () => {
    renderWith([
      failure({ filename: 'big.jpg', size: 30 * MB, errorCode: 'too_large', retryable: false }),
      failure({ filename: 'doc.pdf', errorCode: 'unsupported_format', retryable: false }),
      failure({ filename: 'twin.jpg', errorCode: 'duplicate', retryable: false }),
      failure({ filename: 'flaky.jpg', errorCode: 'processing_failed' }),
    ])

    expect(
      await screen.findByText('failure.tooLarge {"name":"big.jpg","limit":20}')
    ).toBeInTheDocument()
    expect(screen.getByText('failure.unsupportedFormat {"name":"doc.pdf"}')).toBeInTheDocument()
    expect(screen.getByText('failure.duplicate {"name":"twin.jpg"}')).toBeInTheDocument()
    expect(screen.getByText('failure.generic {"name":"flaky.jpg"}')).toBeInTheDocument()
    expect(screen.queryByText('server english')).not.toBeInTheDocument()
    expect(document.querySelector('[title="server english"]')).toBeNull()
  })

  it('does not quote the app limit for a file the proxy rejected below it', async () => {
    renderWith([
      failure({ filename: 'mid.jpg', size: 5 * MB, errorCode: 'too_large', retryable: false }),
    ])

    expect(
      await screen.findByText('failure.tooLargeForServer {"name":"mid.jpg"}')
    ).toBeInTheDocument()
  })

  it('hides every retry action when all failures are permanent but keeps dismiss', async () => {
    renderWith([
      failure({ filename: 'big.jpg', size: 30 * MB, errorCode: 'too_large', retryable: false }),
      failure({ filename: 'doc.pdf', errorCode: 'unsupported_format', retryable: false }),
    ])

    await screen.findByText('failure.unsupportedFormat {"name":"doc.pdf"}')
    expect(screen.queryByText('retryAll')).not.toBeInTheDocument()
    expect(screen.queryByText('retry')).not.toBeInTheDocument()
    expect(screen.getAllByText('dismiss')).toHaveLength(2)

    fireEvent.click(screen.getByText('dismissAll'))
    expect(manager.dismissAll).toHaveBeenCalledTimes(1)
  })

  it('offers retry only on retryable rows and retry all when any is retryable', async () => {
    renderWith([
      failure({
        id: 'big',
        filename: 'big.jpg',
        size: 30 * MB,
        errorCode: 'too_large',
        retryable: false,
      }),
      failure({ id: 'net', filename: 'net.jpg' }),
    ])

    await screen.findByText('failure.generic {"name":"net.jpg"}')
    const retryButtons = screen.getAllByText('retry')
    expect(retryButtons).toHaveLength(1)
    fireEvent.click(retryButtons[0])
    expect(manager.retry).toHaveBeenCalledWith('net')

    fireEvent.click(screen.getByText('retryAll'))
    await waitFor(() => expect(manager.retryAll).toHaveBeenCalledTimes(1))
  })
})
