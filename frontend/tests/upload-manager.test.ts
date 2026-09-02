// @vitest-environment node
import 'fake-indexeddb/auto'
import { IDBFactory } from 'fake-indexeddb'
import { QueryClient } from '@tanstack/react-query'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { enqueueFiles, getPendingUploads, markUploading } from '@/lib/upload-queue'
import * as manager from '@/lib/upload-manager'

// This file runs in the node environment (not jsdom, see the directive
// above) - jsdom's FormData rejects a Blob that round-tripped through
// fake-indexeddb's structured-clone and came back as a different Blob
// implementation. Node's own File/Blob/FormData/fetch don't have that
// cross-realm identity problem, and the manager's logic under test has no
// DOM dependency anyway.
function makeFile(name: string): File {
  return new File(['x'], name, { type: 'image/jpeg' })
}

function makeSizedFile(name: string, sizeBytes: number): File {
  return new File([new Uint8Array(sizeBytes)], name, { type: 'image/jpeg' })
}

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => body,
  } as Response
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  vi.restoreAllMocks()
  vi.spyOn(globalThis, 'fetch')
  manager.init(new QueryClient())
})

describe('startDrain', () => {
  it('uploads staged records and removes them from the queue on success', async () => {
    await enqueueFiles([makeFile('a.jpg')], false)
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        total: 1,
        successful: 1,
        failed: 0,
        results: [{ filename: 'a.jpg', success: true }],
      })
    )

    await manager.startDrain()

    expect(await getPendingUploads()).toHaveLength(0)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('treats a duplicate result as done, not a failure', async () => {
    await enqueueFiles([makeFile('a.jpg')], false)
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        total: 1,
        successful: 1,
        failed: 0,
        results: [
          { filename: 'a.jpg', success: true, duplicate: true, existing_item_id: 'x' },
        ],
      })
    )

    await manager.startDrain()

    expect(await getPendingUploads()).toHaveLength(0)
  })

  it('marks a per-file validation failure terminal, visible in state', async () => {
    await enqueueFiles([makeFile('bad.jpg')], false)
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        total: 1,
        successful: 0,
        failed: 1,
        results: [{ filename: 'bad.jpg', success: false, error: 'Invalid image format' }],
      })
    )

    await manager.startDrain()

    const state = await manager.getState()
    expect(state.terminalRecords).toHaveLength(1)
    expect(state.terminalRecords[0].lastError).toBe('Invalid image format')
  })

  it('retries a whole-chunk network failure and eventually gives up as terminal', async () => {
    const dateSpy = vi.spyOn(Date, 'now')
    try {
      let now = Date.now()
      dateSpy.mockImplementation(() => now)

      await enqueueFiles([makeFile('a.jpg')], false)
      vi.mocked(fetch).mockRejectedValue(new Error('network down'))

      await manager.startDrain()
      let state = await manager.getState()
      expect(state.terminalRecords).toHaveLength(0)
      expect(state.remaining).toBe(1)

      // Each retry is gated by a backoff on updatedAt - advance the clock
      // past it before each subsequent drain pass, simulating separate
      // app-open sessions rather than a tight in-process loop.
      for (let i = 0; i < 5; i++) {
        now += 10 * 60 * 1000
        await manager.startDrain()
      }

      state = await manager.getState()
      expect(state.terminalRecords).toHaveLength(1)
    } finally {
      dateSpy.mockRestore()
    }
  })

  it('splits and retries within the server limit instead of failing the whole chunk', async () => {
    await enqueueFiles(
      [makeFile('a.jpg'), makeFile('b.jpg'), makeFile('c.jpg'), makeFile('d.jpg')],
      false
    )

    // setup.ts assigns global.fetch = vi.fn() once per file; the per-test
    // vi.spyOn in this file's beforeEach layers on top of that same mock, so
    // its call history isn't fully reset between tests without an explicit
    // mockReset() here.
    vi.mocked(fetch).mockReset()
    let n = 0
    vi.mocked(fetch).mockImplementation(async () => {
      n += 1
      if (n === 1) return jsonResponse({ detail: 'Maximum 2 images per bulk upload' }, false, 400)
      if (n === 2)
        return jsonResponse({
          total: 2,
          successful: 2,
          failed: 0,
          results: [
            { filename: 'a.jpg', success: true },
            { filename: 'b.jpg', success: true },
          ],
        })
      if (n === 3)
        return jsonResponse({
          total: 2,
          successful: 2,
          failed: 0,
          results: [
            { filename: 'c.jpg', success: true },
            { filename: 'd.jpg', success: true },
          ],
        })
      throw new Error(`unexpected extra fetch call #${n}`)
    })

    await manager.startDrain()

    expect(await getPendingUploads()).toHaveLength(0)
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('is idempotent - a concurrent call while draining does not start a second loop', async () => {
    // isDraining is set synchronously before startDrain's first await, so
    // the guard doesn't depend on fetch timing - no need to hand-pause the
    // network call to prove it; two calls racing against an instantly
    // resolving mock is enough to show only one drain loop ever ran.
    await enqueueFiles([makeFile('a.jpg'), makeFile('b.jpg')], false)
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        total: 2,
        successful: 2,
        failed: 0,
        results: [
          { filename: 'a.jpg', success: true },
          { filename: 'b.jpg', success: true },
        ],
      })
    )

    // A prior test's backoff-driven retries can still be settling in the
    // background when this one starts (startDrain's retry loop isn't
    // cancellable) - clear the call count right before the actual
    // assertion window so only this test's own calls are counted.
    vi.mocked(fetch).mockClear()
    await Promise.all([manager.startDrain(), manager.startDrain()])

    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('splits a chunk by byte budget, not just file count, to stay under nginx\'s body-size cap', async () => {
    // Three ~6MB files: the first two (12MB) fit under the 15MB budget, the
    // third would push it to 18MB, so it must land in its own request.
    const sixMb = 6 * 1024 * 1024
    await enqueueFiles(
      [
        makeSizedFile('a.jpg', sixMb),
        makeSizedFile('b.jpg', sixMb),
        makeSizedFile('c.jpg', sixMb),
      ],
      false
    )

    vi.mocked(fetch).mockReset()
    const chunkSizes: number[] = []
    vi.mocked(fetch).mockImplementation(async (_url, init) => {
      const formData = init?.body as FormData
      const files = formData.getAll('images')
      chunkSizes.push(files.length)
      return jsonResponse({
        total: files.length,
        successful: files.length,
        failed: 0,
        results: files.map((f) => ({ filename: (f as File).name, success: true })),
      })
    })

    await manager.startDrain()

    expect(await getPendingUploads()).toHaveLength(0)
    expect(chunkSizes).toEqual([2, 1])
  })

  it('invalidates the items query after each chunk', async () => {
    const queryClient = new QueryClient()
    const spy = vi.spyOn(queryClient, 'invalidateQueries')
    manager.init(queryClient)

    await enqueueFiles([makeFile('a.jpg')], false)
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        total: 1,
        successful: 1,
        failed: 0,
        results: [{ filename: 'a.jpg', success: true }],
      })
    )

    await manager.startDrain()

    expect(spy).toHaveBeenCalledWith({ queryKey: ['items'] })
  })
})

describe('backoff reschedule', () => {
  it('resumes on its own once the backoff window elapses, instead of wedging until an external trigger', async () => {
    // vi.useFakeTimers() would also stall fake-indexeddb's internal
    // scheduling (see upload-queue.test.ts), so this captures the real
    // setTimeout call and invokes its callback manually instead of waiting
    // out the real delay.
    const dateSpy = vi.spyOn(Date, 'now')
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    try {
      let now = Date.now()
      dateSpy.mockImplementation(() => now)

      await enqueueFiles([makeFile('a.jpg')], false)
      vi.mocked(fetch).mockRejectedValueOnce(new Error('network down'))

      await manager.startDrain()
      let state = await manager.getState()
      expect(state.terminalRecords).toHaveLength(0)
      expect(state.remaining).toBe(1)
      // The drain loop must exit (not spin/sleep) once nothing is
      // immediately actionable, so the UI doesn't show a stuck spinner for
      // the whole backoff wait.
      expect(state.draining).toBe(false)

      const scheduled = timeoutSpy.mock.calls.find(
        ([, delay]) => typeof delay === 'number' && delay > 0
      )
      expect(scheduled).toBeDefined()
      const [callback] = scheduled!

      vi.mocked(fetch).mockResolvedValueOnce(
        jsonResponse({
          total: 1,
          successful: 1,
          failed: 0,
          results: [{ filename: 'a.jpg', success: true }],
        })
      )
      now += 5000 // past the one-attempt backoff window the timer was armed for

      // Nothing external calls startDrain() here - only the manager's own
      // reschedule, fired by invoking the timer callback it armed.
      ;(callback as () => void)()
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 0))
      }

      expect(await getPendingUploads()).toHaveLength(0)
    } finally {
      dateSpy.mockRestore()
      timeoutSpy.mockRestore()
    }
  })
})

describe('retry/dismiss actions', () => {
  it('retry() clears terminal state and re-drains a single record', async () => {
    await enqueueFiles([makeFile('bad.jpg')], false)
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        total: 1,
        successful: 0,
        failed: 1,
        results: [{ filename: 'bad.jpg', success: false, error: 'transient' }],
      })
    )
    await manager.startDrain()
    const [{ id }] = (await manager.getState()).terminalRecords

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        total: 1,
        successful: 1,
        failed: 0,
        results: [{ filename: 'bad.jpg', success: true }],
      })
    )
    await manager.retry(id)
    // retry() kicks off startDrain() without awaiting it (a UI action
    // shouldn't block on the network) - give the background chain enough
    // ticks to reach fetch, resolve, and settle the record.
    for (let i = 0; i < 10; i++) {
      await new Promise((r) => setTimeout(r, 0))
    }

    expect(await getPendingUploads()).toHaveLength(0)
  })

  it('cancelAll clears a stuck non-terminal record, which has no other recovery path', async () => {
    // A record left in 'pending'/'uploading' never becomes terminal on its
    // own (e.g. a durable write that silently failed to land) - dismissAll
    // only touches terminalRecords, so cancelAll is the only way out.
    await enqueueFiles([makeFile('stuck.jpg')], false)
    const [record] = await getPendingUploads()
    await markUploading(record.id)
    expect((await manager.getState()).remaining).toBe(1)

    await manager.cancelAll()

    expect(await getPendingUploads()).toHaveLength(0)
  })

  it('dismissAll removes every terminal record without retrying', async () => {
    await enqueueFiles([makeFile('bad.jpg')], false)
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        total: 1,
        successful: 0,
        failed: 1,
        results: [{ filename: 'bad.jpg', success: false, error: 'bad' }],
      })
    )
    await manager.startDrain()
    expect((await manager.getState()).terminalRecords).toHaveLength(1)

    await manager.dismissAll()

    expect(await getPendingUploads()).toHaveLength(0)
  })
})
