import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// The .invalid TLD is reserved by RFC 2606 and is where the backend parks a reclaimed
// account's address, so such an address must never be offered as a delivery target.
export function isDeliverableEmail(email: string | null | undefined): email is string {
  return !!email && !email.trim().toLowerCase().endsWith('.invalid');
}

export function chunkArray<T>(items: T[], size: number): T[][] {
  if (size <= 0) return [items];
  const chunks: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size));
  }
  return chunks;
}

// Invariant: the returned Date's local fields hold the wall clock in `timezone`, so getDay() and
// getHours() read that zone's time; its instant is not the real one.
export function getWallClockInTimezone(timezone: string = 'UTC'): Date {
  const now = new Date();
  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(now);
    const field = (type: Intl.DateTimeFormatPartTypes) =>
      parseInt(parts.find((p) => p.type === type)?.value || '0');
    return new Date(field('year'), field('month') - 1, field('day'), field('hour'), field('minute'));
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
    return new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours(), now.getMinutes());
  }
}

export function getTodayInTimezone(timezone: string = 'UTC'): Date {
  const clock = getWallClockInTimezone(timezone);
  return new Date(clock.getFullYear(), clock.getMonth(), clock.getDate());
}

export function getTodayDateStringInTimezone(timezone: string = 'UTC'): string {
  const today = getTodayInTimezone(timezone);
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${today.getFullYear()}-${month}-${day}`;
}

// Mirrors resolve_timezone in backend/app/utils/timezone.py: a missing or unknown zone is UTC, so the
// browser and the server agree on which day "today" is.
export function resolveTimezone(name: string | null | undefined): string {
  if (!name) return 'UTC';
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: name });
    return name;
  } catch {
    return 'UTC';
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

const DATE_KEY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

const SHORT_DATE_OPTIONS: Intl.DateTimeFormatOptions = {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
};

// Built from the local calendar fields, not toISOString(), because the UTC day
// differs from the user's day for several hours around midnight.
export function formatDateKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

// A bare YYYY-MM-DD goes through parseDateString because new Date() would read
// it as UTC midnight and show the previous day west of UTC.
function toDate(value: string | Date): Date {
  if (value instanceof Date) return value;
  return DATE_KEY_PATTERN.test(value) ? parseDateString(value) : new Date(value);
}

export function formatDate(
  value: string | Date,
  locale: string,
  options?: Intl.DateTimeFormatOptions
): string {
  return toDate(value).toLocaleDateString(locale, options);
}

export function formatShortDate(value: string | Date, locale: string): string {
  return formatDate(value, locale, SHORT_DATE_OPTIONS);
}

const MS_PER_DAY = 1000 * 60 * 60 * 24;

// Taken from the local calendar fields through Date.UTC so that a daylight-saving
// change between the two dates cannot make a day 23 or 25 hours long.
function calendarDayNumber(date: Date): number {
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / MS_PER_DAY;
}

// `today` is a date key from the user's profile timezone, not the browser clock, so that
// "today" and "tomorrow" agree with every other date the app derives from useUserToday().
export function formatRelativeDate(value: string | Date, locale: string, today: string): string {
  const days = calendarDayNumber(toDate(value)) - calendarDayNumber(parseDateString(today));
  const format = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const distance = Math.abs(days);
  if (distance < 7) return format.format(days, 'day');
  if (distance < 30) return format.format(Math.round(days / 7), 'week');
  if (distance < 365) return format.format(Math.round(days / 30), 'month');
  return format.format(Math.round(days / 365), 'year');
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
  // Both dates are local midnights, so a daylight-saving change between them makes the gap
  // 23 or 25 hours; rounding to avoid counting that as a partial day.
  const diffTime = today.getTime() - targetDate.getTime();
  return Math.round(diffTime / (1000 * 60 * 60 * 24));
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
