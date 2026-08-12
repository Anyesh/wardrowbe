import { describe, it, expect } from 'vitest'
import { tagProcessingLabel, formatAnalyzingElapsed } from '@/lib/hooks/use-items'

describe('tagProcessingLabel', () => {
  it('reports queued when ai_started_at is not set', () => {
    expect(tagProcessingLabel({ ai_started_at: null })).toBe('queued')
    expect(tagProcessingLabel({ ai_started_at: undefined })).toBe('queued')
  })

  it('reports analyzing when ai_started_at is set', () => {
    expect(tagProcessingLabel({ ai_started_at: '2026-08-12T10:00:00Z' })).toBe('analyzing')
  })
})

describe('formatAnalyzingElapsed', () => {
  it('formats sub-minute elapsed time in seconds', () => {
    const started = '2026-08-12T10:00:00.000Z'
    const now = new Date('2026-08-12T10:00:45.000Z').getTime()
    expect(formatAnalyzingElapsed(started, now)).toBe('45s')
  })

  it('formats elapsed time over a minute as minutes and seconds', () => {
    const started = '2026-08-12T10:00:00.000Z'
    const now = new Date('2026-08-12T10:02:30.000Z').getTime()
    expect(formatAnalyzingElapsed(started, now)).toBe('2m 30s')
  })

  it('never goes negative when the clock is slightly behind the server', () => {
    const started = '2026-08-12T10:00:05.000Z'
    const now = new Date('2026-08-12T10:00:00.000Z').getTime()
    expect(formatAnalyzingElapsed(started, now)).toBe('0s')
  })
})
