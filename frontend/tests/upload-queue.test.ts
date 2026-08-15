import 'fake-indexeddb/auto'
import { IDBFactory } from 'fake-indexeddb'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  enqueueFiles,
  getPendingUploads,
  markDone,
  markRetryable,
  markTerminal,
  markPendingForRetry,
  dismiss,
  purgeAbandoned,
  requestPersistedStorage,
  getStoragePersisted,
} from '@/lib/upload-queue'

function makeFile(name: string, content = 'x', lastModified = 1000): File {
  return new File([content], name, { type: 'image/jpeg', lastModified })
}

beforeEach(() => {
  // Fresh store per test - fake-indexeddb otherwise persists across tests
  // in the same run since the DB name is fixed by the module under test.
  globalThis.indexedDB = new IDBFactory()
})

describe('enqueueFiles', () => {
  it('stages each file and returns one id per file', async () => {
    const { staged, unprotected } = await enqueueFiles(
      [makeFile('a.jpg'), makeFile('b.jpg')],
      false
    )
    expect(staged).toHaveLength(2)
    expect(unprotected).toHaveLength(0)

    const pending = await getPendingUploads()
    expect(pending).toHaveLength(2)
    expect(pending.map((r) => r.filename).sort()).toEqual(['a.jpg', 'b.jpg'])
    expect(pending.every((r) => r.status === 'pending')).toBe(true)
  })

  it('reuses an existing non-terminal record instead of duplicating on reselect', async () => {
    const file = makeFile('shirt.jpg')
    const first = await enqueueFiles([file], false)
    const second = await enqueueFiles([file], false)

    expect(second.staged).toEqual(first.staged)
    const pending = await getPendingUploads()
    expect(pending).toHaveLength(1)
  })

  it('does not reuse a terminal record - reselecting after a real failure stages fresh', async () => {
    const file = makeFile('shirt.jpg')
    const { staged } = await enqueueFiles([file], false)
    await markTerminal(staged[0], 'invalid format')

    const retry = await enqueueFiles([file], false)
    expect(retry.staged[0]).not.toBe(staged[0])
  })

  it('falls back to unprotected when indexedDB is unavailable, without throwing', async () => {
    const original = globalThis.indexedDB
    // @ts-expect-error - simulating an environment without IndexedDB
    delete globalThis.indexedDB
    try {
      const { staged, unprotected } = await enqueueFiles([makeFile('a.jpg')], false)
      expect(staged).toHaveLength(0)
      expect(unprotected).toHaveLength(1)
    } finally {
      globalThis.indexedDB = original
    }
  })
})

describe('status transitions', () => {
  it('markDone deletes the record entirely (blob not kept around)', async () => {
    const { staged } = await enqueueFiles([makeFile('a.jpg')], false)
    await markDone(staged[0])
    expect(await getPendingUploads()).toHaveLength(0)
  })

  it('markRetryable increments attempts and returns the record to pending', async () => {
    const { staged } = await enqueueFiles([makeFile('a.jpg')], false)
    await markRetryable(staged[0], 'network error')
    await markRetryable(staged[0], 'network error again')

    const [record] = await getPendingUploads()
    expect(record.status).toBe('pending')
    expect(record.terminal).toBe(false)
    expect(record.attempts).toBe(2)
    expect(record.lastError).toBe('network error again')
  })

  it('markTerminal marks failed and terminal, keeps the record visible', async () => {
    const { staged } = await enqueueFiles([makeFile('a.jpg')], false)
    await markTerminal(staged[0], 'invalid image format')

    const [record] = await getPendingUploads()
    expect(record.status).toBe('failed')
    expect(record.terminal).toBe(true)
    expect(record.lastError).toBe('invalid image format')
  })

  it('markPendingForRetry resets attempts, unlike the automatic-retry path', async () => {
    const { staged } = await enqueueFiles([makeFile('a.jpg')], false)
    await markRetryable(staged[0], 'network blip')
    await markRetryable(staged[0], 'network blip again')

    await markPendingForRetry(staged[0])

    const [record] = await getPendingUploads()
    expect(record.status).toBe('pending')
    expect(record.attempts).toBe(0)
    expect(record.lastError).toBeNull()
  })

  it('dismiss removes a pending or failed record', async () => {
    const { staged } = await enqueueFiles([makeFile('a.jpg')], false)
    await markTerminal(staged[0], 'bad file')
    await dismiss(staged[0])
    expect(await getPendingUploads()).toHaveLength(0)
  })
})

describe('purgeAbandoned', () => {
  it('removes only records older than the given TTL', async () => {
    // vi.useFakeTimers() would also stall fake-indexeddb's internal
    // scheduling, so only Date.now() is mocked here, not the event loop.
    const dateSpy = vi.spyOn(Date, 'now')
    try {
      const base = new Date('2026-01-01T00:00:00Z').getTime()
      dateSpy.mockReturnValue(base)
      const { staged: oldStaged } = await enqueueFiles([makeFile('old.jpg')], false)

      dateSpy.mockReturnValue(base + 9000)
      const { staged: freshStaged } = await enqueueFiles([makeFile('fresh.jpg')], false)

      dateSpy.mockReturnValue(base + 10_000)
      await purgeAbandoned(5000)

      const remaining = await getPendingUploads()
      expect(remaining.map((r) => r.id)).toEqual(freshStaged)
      expect(remaining.map((r) => r.id)).not.toEqual(
        expect.arrayContaining(oldStaged)
      )
    } finally {
      dateSpy.mockRestore()
    }
  })
})

describe('storage persistence', () => {
  it('caches the persist() grant and getStoragePersisted reads it back', async () => {
    Object.defineProperty(globalThis.navigator, 'storage', {
      configurable: true,
      value: { persist: vi.fn().mockResolvedValue(true) },
    })

    expect(await getStoragePersisted()).toBeNull()
    const granted = await requestPersistedStorage()
    expect(granted).toBe(true)
    expect(await getStoragePersisted()).toBe(true)
  })

  it('returns false without throwing when storage.persist is unsupported', async () => {
    Object.defineProperty(globalThis.navigator, 'storage', {
      configurable: true,
      value: {},
    })
    expect(await requestPersistedStorage()).toBe(false)
  })
})
