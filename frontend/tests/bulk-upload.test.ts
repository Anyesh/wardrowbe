import React from 'react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  mergeBulkUploadResponses,
  uploadFilesWithinServerLimit,
  useBulkCreateItems,
} from '@/lib/hooks/use-items'
import type { BulkUploadResponse } from '@/lib/hooks/use-items'
import { fetchBulkUploadLimit } from '@/lib/hooks/use-features'
import { queryKeys } from '@/lib/hooks/query-keys'

// Minimal fake XHR standing in for uploadBulkItemsChunk's XMLHttpRequest use -
// queues one canned response per call, replayed on send() via a `load` event.
class FakeXhr {
  static queue: Array<{ status: number; body: unknown }> = []
  static sentImageCounts: number[] = []
  upload = { addEventListener: () => {} }
  status = 0
  responseText = ''
  private listeners: Record<string, Array<() => void>> = {}
  open() {}
  setRequestHeader() {}
  addEventListener(event: string, handler: () => void) {
    ;(this.listeners[event] ??= []).push(handler)
  }
  send(body: FormData) {
    FakeXhr.sentImageCounts.push(body.getAll('images').length)
    const next = FakeXhr.queue.shift()
    if (!next) throw new Error('FakeXhr.queue exhausted')
    this.status = next.status
    this.responseText = JSON.stringify(next.body)
    this.listeners['load']?.forEach((fn) => fn())
  }
}

describe('mergeBulkUploadResponses', () => {
  it('should sum counts and concatenate results across chunks', () => {
    const chunkA: BulkUploadResponse = {
      total: 2,
      successful: 2,
      failed: 0,
      results: [
        { filename: 'a.jpg', success: true },
        { filename: 'b.jpg', success: true },
      ],
    }
    const chunkB: BulkUploadResponse = {
      total: 1,
      successful: 0,
      failed: 1,
      results: [{ filename: 'c.jpg', success: false, error: 'bad image' }],
    }

    const merged = mergeBulkUploadResponses([chunkA, chunkB])

    expect(merged.total).toBe(3)
    expect(merged.successful).toBe(2)
    expect(merged.failed).toBe(1)
    expect(merged.results).toEqual([...chunkA.results, ...chunkB.results])
  })

  it('should return zeroed response for no chunks', () => {
    const merged = mergeBulkUploadResponses([])
    expect(merged).toEqual({ total: 0, successful: 0, failed: 0, results: [] })
  })

  it('should preserve per-file results when every chunk fully fails', () => {
    const chunk: BulkUploadResponse = {
      total: 2,
      successful: 0,
      failed: 2,
      results: [
        { filename: 'a.jpg', success: false, error: 'Network error' },
        { filename: 'b.jpg', success: false, error: 'Network error' },
      ],
    }

    const merged = mergeBulkUploadResponses([chunk])

    expect(merged.successful).toBe(0)
    expect(merged.failed).toBe(2)
    expect(merged.results).toHaveLength(2)
  })
})

describe('uploadFilesWithinServerLimit', () => {
  let originalXhr: typeof XMLHttpRequest

  beforeEach(() => {
    originalXhr = globalThis.XMLHttpRequest
    FakeXhr.queue = []
    FakeXhr.sentImageCounts = []
    // @ts-expect-error - test double stands in for the real constructor
    globalThis.XMLHttpRequest = FakeXhr
  })

  afterEach(() => {
    globalThis.XMLHttpRequest = originalXhr
  })

  it('splits a chunk on the server-reported limit instead of failing every file', async () => {
    const files = [
      new File(['a'], 'a.jpg'),
      new File(['b'], 'b.jpg'),
      new File(['c'], 'c.jpg'),
    ]

    FakeXhr.queue.push(
      { status: 400, body: { detail: 'Maximum 2 images per bulk upload' } },
      {
        status: 201,
        body: {
          total: 2,
          successful: 2,
          failed: 0,
          results: [
            { filename: 'a.jpg', success: true },
            { filename: 'b.jpg', success: true },
          ],
        },
      },
      {
        status: 201,
        body: {
          total: 1,
          successful: 1,
          failed: 0,
          results: [{ filename: 'c.jpg', success: true }],
        },
      }
    )

    const result = await uploadFilesWithinServerLimit(files, false, 'token', vi.fn())

    expect(result.total).toBe(3)
    expect(result.successful).toBe(3)
    expect(result.results.map((r) => r.filename)).toEqual(['a.jpg', 'b.jpg', 'c.jpg'])
  })

  it('propagates a non-limit error without splitting', async () => {
    const files = [new File(['a'], 'a.jpg')]
    FakeXhr.queue.push({ status: 500, body: { detail: 'Internal error' } })

    await expect(uploadFilesWithinServerLimit(files, false, 'token', vi.fn())).rejects.toThrow(
      'Internal error'
    )
  })
})

function successBody(names: string[]) {
  return {
    total: names.length,
    successful: names.length,
    failed: 0,
    results: names.map((filename) => ({ filename, success: true })),
  }
}

function clientWithFeatures(features?: Record<string, unknown>): QueryClient {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  if (features) client.setQueryData(queryKeys.features, features)
  return client
}

describe('fetchBulkUploadLimit', () => {
  it('reads max_bulk_upload_count from the features query', async () => {
    const client = clientWithFeatures({ background_removal: false, max_bulk_upload_count: 2 })
    expect(await fetchBulkUploadLimit(client)).toBe(2)
  })

  it('returns null when the server does not report a limit', async () => {
    const client = clientWithFeatures({ background_removal: false })
    expect(await fetchBulkUploadLimit(client)).toBeNull()
  })

  it('returns null when the features request fails', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
    expect(await fetchBulkUploadLimit(clientWithFeatures())).toBeNull()
  })
})

describe('useBulkCreateItems', () => {
  let originalXhr: typeof XMLHttpRequest

  beforeEach(() => {
    originalXhr = globalThis.XMLHttpRequest
    FakeXhr.queue = []
    FakeXhr.sentImageCounts = []
    // @ts-expect-error - test double stands in for the real constructor
    globalThis.XMLHttpRequest = FakeXhr
  })

  afterEach(() => {
    globalThis.XMLHttpRequest = originalXhr
  })

  function renderWith(client: QueryClient) {
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client }, children)
    return renderHook(() => useBulkCreateItems(), { wrapper })
  }

  it('chunks by the limit the features endpoint reports, without a rejected request first', async () => {
    const client = clientWithFeatures({ background_removal: false, max_bulk_upload_count: 2 })
    FakeXhr.queue.push(
      { status: 201, body: successBody(['a.jpg', 'b.jpg']) },
      { status: 201, body: successBody(['c.jpg']) }
    )
    const { result } = renderWith(client)
    const files = ['a.jpg', 'b.jpg', 'c.jpg'].map((name) => new File(['x'], name))

    let outcome: Awaited<ReturnType<typeof result.current.mutateAsync>> | undefined
    await act(async () => {
      outcome = await result.current.mutateAsync({ files })
    })

    expect(FakeXhr.sentImageCounts).toEqual([2, 1])
    expect(outcome?.unprotected?.successful).toBe(3)
  })

  it('falls back to the default chunk when the features request fails', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
    FakeXhr.queue.push({ status: 201, body: successBody(['a.jpg', 'b.jpg', 'c.jpg']) })
    const { result } = renderWith(clientWithFeatures())
    const files = ['a.jpg', 'b.jpg', 'c.jpg'].map((name) => new File(['x'], name))

    await act(async () => {
      await result.current.mutateAsync({ files })
    })

    expect(FakeXhr.sentImageCounts).toEqual([3])
  })
})
