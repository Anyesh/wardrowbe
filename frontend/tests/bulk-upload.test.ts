import { describe, it, expect } from 'vitest'
import { mergeBulkUploadResponses } from '@/lib/hooks/use-items'
import type { BulkUploadResponse } from '@/lib/hooks/use-items'

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
