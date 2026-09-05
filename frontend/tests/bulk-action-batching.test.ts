import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

interface RotateResponse {
  queued: number
  failed: number
  errors: string[]
  next_cursor?: string | null
  has_more?: boolean
}

const SUM_KEYS: (keyof RotateResponse)[] = ['queued', 'failed']

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

// Each test re-imports the module so the learned server limit, which is cached
// at module scope on purpose, does not leak between cases.
async function freshDrain() {
  vi.resetModules()
  const mod = await import('@/lib/hooks/use-items')
  return mod.drainBulkAction
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function bodyOf(call: unknown[]) {
  return JSON.parse((call[1] as RequestInit).body as string)
}

describe('drainBulkAction with an explicit id list', () => {
  it('sends the list as one request when the server accepts it', async () => {
    const drain = await freshDrain()
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ queued: 3, failed: 0, errors: [], has_more: false, next_cursor: null })
    )

    const result = await drain<RotateResponse>(
      '/items/bulk/rotate',
      { item_ids: ['a', 'b', 'c'] },
      SUM_KEYS
    )

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(result.queued).toBe(3)
  })

  it('learns the server limit from a rejection and re-sends in chunks', async () => {
    const drain = await freshDrain()
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ detail: 'Maximum 2 items per bulk action' }, 400)
      )
      .mockResolvedValueOnce(
        jsonResponse({ queued: 2, failed: 0, errors: [], has_more: false, next_cursor: null })
      )
      .mockResolvedValueOnce(
        jsonResponse({ queued: 1, failed: 0, errors: [], has_more: false, next_cursor: null })
      )

    const result = await drain<RotateResponse>(
      '/items/bulk/rotate',
      { item_ids: ['a', 'b', 'c'] },
      SUM_KEYS
    )

    expect(result.queued).toBe(3)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(bodyOf(fetchMock.mock.calls[1]).item_ids).toEqual(['a', 'b'])
    expect(bodyOf(fetchMock.mock.calls[2]).item_ids).toEqual(['c'])
  })

  it('reuses the learned limit on a later action instead of failing again', async () => {
    const drain = await freshDrain()
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: 'Maximum 2 items per bulk action' }, 400))
      .mockResolvedValue(
        jsonResponse({ queued: 1, failed: 0, errors: [], has_more: false, next_cursor: null })
      )

    await drain<RotateResponse>('/items/bulk/rotate', { item_ids: ['a', 'b', 'c'] }, SUM_KEYS)
    fetchMock.mockClear()
    await drain<RotateResponse>('/items/bulk/rotate', { item_ids: ['d', 'e', 'f'] }, SUM_KEYS)

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(bodyOf(fetchMock.mock.calls[0]).item_ids).toEqual(['d', 'e'])
    expect(bodyOf(fetchMock.mock.calls[1]).item_ids).toEqual(['f'])
  })

  it('propagates a 400 that is not the bulk limit', async () => {
    const drain = await freshDrain()
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'Item has no image' }, 400))

    await expect(
      drain<RotateResponse>('/items/bulk/rotate', { item_ids: ['a'] }, SUM_KEYS)
    ).rejects.toThrow('Item has no image')
  })

  it('sums counts and concatenates errors across chunks', async () => {
    const drain = await freshDrain()
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: 'Maximum 2 items per bulk action' }, 400))
      .mockResolvedValueOnce(
        jsonResponse({ queued: 1, failed: 1, errors: ['bad a'], has_more: false, next_cursor: null })
      )
      .mockResolvedValueOnce(
        jsonResponse({ queued: 0, failed: 1, errors: ['bad c'], has_more: false, next_cursor: null })
      )

    const result = await drain<RotateResponse>(
      '/items/bulk/rotate',
      { item_ids: ['a', 'b', 'c'] },
      SUM_KEYS
    )

    expect(result).toMatchObject({ queued: 1, failed: 2, errors: ['bad a', 'bad c'] })
  })
})

describe('drainBulkAction with select_all', () => {
  it('follows the cursor until the server stops reporting more', async () => {
    const drain = await freshDrain()
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ queued: 2, failed: 0, errors: [], has_more: true, next_cursor: 'id-2' })
      )
      .mockResolvedValueOnce(
        jsonResponse({ queued: 2, failed: 0, errors: [], has_more: true, next_cursor: 'id-4' })
      )
      .mockResolvedValueOnce(
        jsonResponse({ queued: 1, failed: 0, errors: [], has_more: false, next_cursor: null })
      )

    const result = await drain<RotateResponse>(
      '/items/bulk/rotate',
      { select_all: true },
      SUM_KEYS
    )

    expect(result.queued).toBe(5)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(bodyOf(fetchMock.mock.calls[0]).after_id).toBeUndefined()
    expect(bodyOf(fetchMock.mock.calls[1]).after_id).toBe('id-2')
    expect(bodyOf(fetchMock.mock.calls[2]).after_id).toBe('id-4')
  })

  it('stops after one request when the first batch covers everything', async () => {
    const drain = await freshDrain()
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ queued: 3, failed: 0, errors: [], has_more: false, next_cursor: null })
    )

    await drain<RotateResponse>('/items/bulk/rotate', { select_all: true }, SUM_KEYS)

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('stops if the server keeps claiming more, so a bad cursor cannot loop forever', async () => {
    const drain = await freshDrain()
    fetchMock.mockResolvedValue(
      jsonResponse({ queued: 1, failed: 0, errors: [], has_more: true, next_cursor: 'stuck' })
    )

    const result = await drain<RotateResponse>(
      '/items/bulk/rotate',
      { select_all: true },
      SUM_KEYS
    )

    expect(fetchMock.mock.calls.length).toBeLessThanOrEqual(201)
    expect(result.has_more).toBe(true)
  })

  it('carries the caller filters into every follow-up batch', async () => {
    const drain = await freshDrain()
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ queued: 1, failed: 0, errors: [], has_more: true, next_cursor: 'id-1' })
      )
      .mockResolvedValueOnce(
        jsonResponse({ queued: 1, failed: 0, errors: [], has_more: false, next_cursor: null })
      )

    await drain<RotateResponse>(
      '/items/bulk/rotate',
      { select_all: true, excluded_ids: ['skip'], filters: { type: 'shirt' } },
      SUM_KEYS
    )

    const second = bodyOf(fetchMock.mock.calls[1])
    expect(second.excluded_ids).toEqual(['skip'])
    expect(second.filters).toEqual({ type: 'shirt' })
  })
})
