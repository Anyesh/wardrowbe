import { describe, it, expect, vi } from 'vitest'
import { cn, formatWornAgo } from '@/lib/utils'

// Mock translation function that returns the key (with params appended if provided)
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
  // Helper: get YYYY-MM-DD in a specific timezone
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
})
