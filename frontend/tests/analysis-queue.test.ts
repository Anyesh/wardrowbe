import { describe, it, expect } from 'vitest'
import { deriveQueueSummary, formatDurationSeconds } from '@/lib/hooks/use-items'
import type { TaggingProgress } from '@/lib/types'

function progress(overrides: Partial<TaggingProgress> = {}): TaggingProgress {
  return {
    processing: 0,
    queued: 0,
    analyzing: 0,
    failed: 0,
    completed: 0,
    total: 0,
    batch_total: 0,
    batch_completed: 0,
    batch_failed: 0,
    current: [],
    recent: [],
    failures: [],
    avg_duration_seconds: null,
    eta_seconds: null,
    concurrency: 1,
    ...overrides,
  }
}

describe('deriveQueueSummary', () => {
  it('measures the running import, not the whole wardrobe', () => {
    // The reported bug: 90 new items dropped into a 200-item wardrobe. Divided
    // wardrobe-wide the run opens at 72% and moves a third of a point per item,
    // which is true and tells the user nothing.
    const summary = deriveQueueSummary(
      progress({
        total: 200,
        completed: 113,
        processing: 87,
        queued: 86,
        analyzing: 1,
        batch_total: 90,
        batch_completed: 3,
      })
    )

    expect(summary.percentComplete).toBe(3)
    expect(summary.batchDone).toBe(3)
    expect(summary.batchTotal).toBe(90)
    expect(summary.remaining).toBe(87)
  })

  it('counts failures as finished so the bar reaches the end of a partly failed run', () => {
    const summary = deriveQueueSummary(
      progress({ batch_total: 10, batch_completed: 7, batch_failed: 3 })
    )

    expect(summary.percentComplete).toBe(100)
    expect(summary.batchDone).toBe(7)
    expect(summary.batchFailed).toBe(3)
  })

  it('reports an empty run rather than dividing by zero', () => {
    expect(deriveQueueSummary(progress()).percentComplete).toBe(0)
    expect(deriveQueueSummary(undefined).percentComplete).toBe(0)
    expect(deriveQueueSummary(undefined).batchTotal).toBe(0)
  })

  it('holds at zero while every item is still queued', () => {
    const summary = deriveQueueSummary(
      progress({ batch_total: 90, queued: 90, processing: 90 })
    )

    expect(summary.percentComplete).toBe(0)
    expect(summary.remaining).toBe(90)
  })
})

describe('formatDurationSeconds', () => {
  it('formats sub-minute durations in seconds', () => {
    expect(formatDurationSeconds(42)).toBe('42s')
  })

  it('formats longer durations as minutes and seconds', () => {
    expect(formatDurationSeconds(150)).toBe('2m 30s')
  })

  it('rounds to whole seconds', () => {
    expect(formatDurationSeconds(41.6)).toBe('42s')
  })

  it('has nothing to show for a missing duration', () => {
    expect(formatDurationSeconds(null)).toBeNull()
    expect(formatDurationSeconds(undefined)).toBeNull()
  })

  it('never renders a negative duration', () => {
    expect(formatDurationSeconds(-5)).toBe('0s')
  })
})
