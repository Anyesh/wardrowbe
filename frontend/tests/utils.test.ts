import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import {
  cn,
  chunkArray,
  formatDate,
  formatDateKey,
  formatRelativeDate,
  formatShortDate,
  formatWornAgo,
  isDeliverableEmail,
} from '@/lib/utils'

const mockT = vi.fn((key: string, params?: Record<string, unknown>) =>
  params ? `${key}:${JSON.stringify(params)}` : key
)

describe('cn utility', () => {
  it('should merge class names', () => {
    const result = cn('text-red-500', 'bg-blue-500')
    expect(result).toBe('text-red-500 bg-blue-500')
  })

  it('should handle conditional classes', () => {
    const isActive = true
    const result = cn('base-class', isActive && 'active-class')
    expect(result).toBe('base-class active-class')
  })

  it('should handle undefined values', () => {
    const result = cn('base-class', undefined, 'another-class')
    expect(result).toBe('base-class another-class')
  })

  it('should merge conflicting Tailwind classes', () => {
    // tailwind-merge should handle conflicts
    const result = cn('p-4', 'p-8')
    expect(result).toBe('p-8')
  })

  it('should handle arrays of classes', () => {
    const result = cn(['class-1', 'class-2'], 'class-3')
    expect(result).toBe('class-1 class-2 class-3')
  })

  it('should handle empty inputs', () => {
    const result = cn()
    expect(result).toBe('')
  })

  it('should handle object notation', () => {
    const result = cn({
      'active': true,
      'disabled': false,
      'visible': true,
    })
    expect(result).toBe('active visible')
  })
})

describe('formatWornAgo', () => {
  const dateStrInTimezone = (timezone: string, offsetDays = 0) => {
    const d = new Date();
    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
    const date = new Date(d);
    date.setDate(date.getDate() + offsetDays);
    return formatter.format(date);
  };

  it('should return "wornAgo.today" when days is 0', () => {
    const dateStr = dateStrInTimezone('UTC');
    mockT.mockClear()
    const result = formatWornAgo(dateStr, 'UTC', mockT)
    expect(result).toBe('wornAgo.today')
    expect(mockT).toHaveBeenCalledWith('wornAgo.today')
  })

  it('should return "wornAgo.yesterday" when days is 1', () => {
    const dateStr = dateStrInTimezone('UTC', -1);
    mockT.mockClear()
    const result = formatWornAgo(dateStr, 'UTC', mockT)
    expect(result).toBe('wornAgo.yesterday')
    expect(mockT).toHaveBeenCalledWith('wornAgo.yesterday')
  })

  it('should return "wornAgo.daysAgo" with days param when days > 1', () => {
    const dateStr = dateStrInTimezone('UTC', -5);
    mockT.mockClear()
    const result = formatWornAgo(dateStr, 'UTC', mockT)
    expect(result).toBe('wornAgo.daysAgo:{"days":5}')
    expect(mockT).toHaveBeenCalledWith('wornAgo.daysAgo', { days: 5 })
  })

  it('should use default translation function when t is not provided', () => {
    const dateStr = dateStrInTimezone('UTC');
    const result = formatWornAgo(dateStr)
    expect(result).toBe('wornAgo.today')
  })

  it('counts whole days across a daylight-saving change in the browser zone', () => {
    const originalTz = process.env.TZ
    process.env.TZ = 'Australia/Sydney'
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-05T03:00:00Z'))
    try {
      expect(formatWornAgo('2026-10-04', 'Australia/Sydney', mockT)).toBe('wornAgo.yesterday')
      expect(formatWornAgo('2026-09-30', 'Australia/Sydney', mockT)).toBe(
        'wornAgo.daysAgo:{"days":5}'
      )
    } finally {
      vi.useRealTimers()
      process.env.TZ = originalTz
    }
  })
})

describe('chunkArray utility', () => {
  it('should split items evenly across chunks', () => {
    const result = chunkArray([1, 2, 3, 4], 2)
    expect(result).toEqual([[1, 2], [3, 4]])
  })

  it('should put remainder items in a final smaller chunk', () => {
    const result = chunkArray([1, 2, 3, 4, 5], 2)
    expect(result).toEqual([[1, 2], [3, 4], [5]])
  })

  it('should return a single chunk when items fit within size', () => {
    const result = chunkArray([1, 2, 3], 20)
    expect(result).toEqual([[1, 2, 3]])
  })

  it('should return an empty array for empty input', () => {
    const result = chunkArray([], 20)
    expect(result).toEqual([])
  })

  it('should not lose or duplicate items across many chunks', () => {
    const items = Array.from({ length: 45 }, (_, i) => i)
    const result = chunkArray(items, 20)
    expect(result).toEqual([
      items.slice(0, 20),
      items.slice(20, 40),
      items.slice(40, 45),
    ])
    expect(result.flat()).toEqual(items)
  })
})

describe('isDeliverableEmail', () => {
  it.each([
    ['user@example.com', true],
    ['abc@detached.invalid', false],
    [' ABC@Detached.INVALID ', false],
    ['', false],
    [undefined, false],
  ])('%j -> %s', (email, expected) => {
    expect(isDeliverableEmail(email)).toBe(expected)
  })
})

describe('date helpers', () => {
  const originalTz = process.env.TZ

  const inTimezone = (tz: string) => {
    process.env.TZ = tz
  }

  afterEach(() => {
    process.env.TZ = originalTz
    vi.useRealTimers()
  })

  describe('formatDateKey', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    it('keeps the local day just before midnight west of UTC', () => {
      inTimezone('America/New_York')
      vi.setSystemTime(new Date('2026-03-15T03:30:00Z'))
      expect(formatDateKey(new Date())).toBe('2026-03-14')
    })

    it('keeps the local day just after midnight east of UTC', () => {
      inTimezone('Asia/Kathmandu')
      vi.setSystemTime(new Date('2026-03-14T20:00:00Z'))
      expect(formatDateKey(new Date())).toBe('2026-03-15')
    })

    it('zero-pads month and day', () => {
      expect(formatDateKey(new Date(2026, 0, 5))).toBe('2026-01-05')
    })

    it('rolls a month-overflow date into the right key', () => {
      expect(formatDateKey(new Date(2026, 2, 0))).toBe('2026-02-28')
    })
  })

  describe('formatShortDate', () => {
    it('formats a date key as the same local calendar day west of UTC', () => {
      inTimezone('America/Los_Angeles')
      expect(formatShortDate('2026-10-05', 'en')).toBe('Mon, Oct 5')
    })

    it('uses the given locale rather than the runtime default', () => {
      expect(formatShortDate('2026-10-05', 'de')).toBe('Mo., 5. Okt.')
    })

    it('accepts a Date', () => {
      expect(formatShortDate(new Date(2026, 9, 5), 'en')).toBe('Mon, Oct 5')
    })
  })

  describe('formatDate', () => {
    it('reads a date key as local, not UTC midnight', () => {
      inTimezone('America/Los_Angeles')
      expect(formatDate('2026-10-05', 'en-US')).toBe('10/5/2026')
    })

    it('reads a timestamp as an instant', () => {
      inTimezone('Asia/Kathmandu')
      expect(formatDate('2026-10-05T20:00:00Z', 'en-US')).toBe('10/6/2026')
    })

    it('passes format options through', () => {
      expect(
        formatDate('2026-10-05', 'en-US', { month: 'short', day: 'numeric', year: 'numeric' })
      ).toBe('Oct 5, 2026')
    })
  })

  describe('formatRelativeDate', () => {
    const now = new Date(2026, 9, 5, 12)

    it.each([
      ['en', ['in 3 days', '3 days ago', 'tomorrow', 'today']],
      ['de', ['in 3 Tagen', 'vor 3 Tagen', 'morgen', 'heute']],
      ['ja', ['3 日後', '3 日前', '明日', '今日']],
    ])('words the distance in calendar days on the %s locale', (locale, expected) => {
      expect(
        ['2026-10-08', '2026-10-02', '2026-10-06', '2026-10-05'].map((key) =>
          formatRelativeDate(key, locale as string, now)
        )
      ).toEqual(expected)
    })

    it('switches to weeks, months and years as the distance grows', () => {
      expect(formatRelativeDate('2026-10-19', 'en', now)).toBe('in 2 weeks')
      expect(formatRelativeDate('2026-08-05', 'en', now)).toBe('2 months ago')
      expect(formatRelativeDate('2025-10-05', 'en', now)).toBe('last year')
    })

    it('counts a day across a daylight-saving change as one day', () => {
      inTimezone('America/New_York')
      expect(formatRelativeDate('2026-03-08', 'en', new Date(2026, 2, 9, 0, 30))).toBe('yesterday')
    })

    it('ignores the time of day of now', () => {
      expect(formatRelativeDate('2026-10-06', 'en', new Date(2026, 9, 5, 23, 59))).toBe('tomorrow')
    })
  })
})
