import { describe, it, expect } from 'vitest'
import {
  DEFAULT_STALE_TIME,
  SLOW_STALE_TIME,
  WEATHER_STALE_TIME,
  processingPollInterval,
} from '@/lib/hooks/query-timing'

describe('query timing', () => {
  it('keeps the stale times the hooks used before', () => {
    expect(DEFAULT_STALE_TIME).toBe(60_000)
    expect(SLOW_STALE_TIME).toBe(300_000)
    expect(WEATHER_STALE_TIME).toBe(900_000)
  })

  it('polls every 5s while processing and every 30s otherwise', () => {
    expect(processingPollInterval(true)).toBe(5_000)
    expect(processingPollInterval(false)).toBe(30_000)
  })
})
