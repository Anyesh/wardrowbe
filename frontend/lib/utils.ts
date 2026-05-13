import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Get today's date in a specific timezone.
 * Returns a Date object representing midnight in the given timezone.
 */
export function getTodayInTimezone(timezone: string = 'UTC'): Date {
  try {
    const now = new Date();
    // Format date in the target timezone to get the local date
    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
    const parts = formatter.formatToParts(now);
    const year = parseInt(parts.find(p => p.type === 'year')?.value || '0');
    const month = parseInt(parts.find(p => p.type === 'month')?.value || '0') - 1;
    const day = parseInt(parts.find(p => p.type === 'day')?.value || '0');
    return new Date(year, month, day);
  } catch {
    // Fallback to local date if timezone is invalid
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }
}

/**
 * Parse a date string (YYYY-MM-DD) to a Date object.
 * Note: The date is parsed as local date, not UTC.
 */
export function parseDateString(dateStr: string): Date {
  // Parse YYYY-MM-DD as local date (not UTC)
  const [year, month, day] = dateStr.split('-').map(Number);
  return new Date(year, month - 1, day);
}

/**
 * Calculate the number of calendar days between a date string and today in the user's timezone.
 * Returns the difference in days where:
 * - 0 = today
 * - 1 = yesterday
 * - n = n days ago
 */
export function getDaysSinceDateInTimezone(dateStr: string, timezone: string = 'UTC'): number {
  const today = getTodayInTimezone(timezone);
  const targetDate = parseDateString(dateStr);
  
  // Calculate difference in days
  const diffTime = today.getTime() - targetDate.getTime();
  const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
  return diffDays;
}

/**
 * Format a "worn X days ago" message based on a date string and user's timezone.
 * Accepts a translation function for i18n support.
 */
export function formatWornAgo(
  dateStr: string,
  timezone: string = 'UTC',
  t: (key: string, params?: Record<string, string | number | Date>) => string = (key, params) =>
    params ? `${key}:${JSON.stringify(params)}` : key
): string {
  const days = getDaysSinceDateInTimezone(dateStr, timezone);
  if (days === 0) return t('wornAgo.today');
  if (days === 1) return t('wornAgo.yesterday');
  return t('wornAgo.daysAgo', { days });
}

/**
 * Get the color class for the "worn X ago" text based on days since worn.
 */
export function getWornAgoColorClass(dateStr: string, timezone: string = 'UTC'): string {
  const days = getDaysSinceDateInTimezone(dateStr, timezone);
  if (days < 7) return 'text-green-600 dark:text-green-400';
  if (days <= 30) return 'text-muted-foreground';
  return 'text-muted-foreground/60';
}
