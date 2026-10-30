import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Schedule } from '@/lib/hooks/use-notifications'
import { findNextSchedule } from '@/lib/schedules'

const originalTz = process.env.TZ

function schedule(overrides: Partial<Schedule>): Schedule {
  return {
    id: 's1',
    user_id: 'u1',
    day_of_week: 0,
    notification_time: '07:00:00',
    occasion: 'casual',
    enabled: true,
    notify_day_before: false,
    created_at: '',
    updated_at: '',
    ...overrides,
  }
}

beforeEach(() => {
  process.env.TZ = 'UTC'
  vi.useFakeTimers({ toFake: ['Date'] })
})

afterEach(() => {
  vi.useRealTimers()
  process.env.TZ = originalTz
})

describe('findNextSchedule', () => {
  it("counts from the profile timezone's clock, not the browser's", () => {
    // 21:00 on Sunday 4 October in Los Angeles is 04:00 on Monday 5 October in UTC.
    vi.setSystemTime(new Date('2026-10-05T04:00:00Z'))
    const s = schedule({ id: 'sun-22', day_of_week: 6, notification_time: '22:00:00' })

    const next = findNextSchedule([s], 'America/Los_Angeles')

    expect(next?.schedule.id).toBe('sun-22')
    expect(next?.daysUntil).toBe(0)
    expect(next?.minutesUntil).toBe(60)
  })

  it('reads day_of_week as Monday-first, like the backend', () => {
    // 09:00 on Monday 5 October in UTC.
    vi.setSystemTime(new Date('2026-10-05T09:00:00Z'))
    const monday = schedule({ id: 'mon', day_of_week: 0, notification_time: '10:00:00' })
    const sunday = schedule({ id: 'sun', day_of_week: 6, notification_time: '10:00:00' })

    const next = findNextSchedule([sunday, monday], 'UTC')

    expect(next?.schedule.id).toBe('mon')
    expect(next?.daysUntil).toBe(0)
    expect(next?.notifyDay).toBe(0)
  })

  it('fires a day-before schedule on the previous day', () => {
    // 09:00 on Monday 5 October in UTC; a Tuesday outfit notified the day before fires today.
    vi.setSystemTime(new Date('2026-10-05T09:00:00Z'))
    const tuesday = schedule({ id: 'tue', day_of_week: 1, notification_time: '20:00:00', notify_day_before: true })

    const next = findNextSchedule([tuesday], 'UTC')

    expect(next?.daysUntil).toBe(0)
    expect(next?.notifyDay).toBe(0)
    expect(next?.minutesUntil).toBe(11 * 60)
  })

  it('skips disabled schedules', () => {
    vi.setSystemTime(new Date('2026-10-05T09:00:00Z'))
    expect(findNextSchedule([schedule({ enabled: false })], 'UTC')).toBeNull()
  })
})
