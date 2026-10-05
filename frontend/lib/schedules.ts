import type { Schedule } from '@/lib/hooks/use-notifications';
import { getWallClockInTimezone } from '@/lib/utils';

export interface NextSchedule {
  schedule: Schedule;
  notifyDay: number;
  daysUntil: number;
  minutesUntil: number;
}

// Weekdays here are Monday-first (0 = Monday), matching Schedule.day_of_week and the
// worker's datetime.weekday(); JS getDay() is Sunday-first and must be converted.
function mondayFirstDay(date: Date): number {
  return (date.getDay() + 6) % 7;
}

export function findNextSchedule(schedules: Schedule[], timezone: string): NextSchedule | null {
  const now = getWallClockInTimezone(timezone);
  const currentDay = mondayFirstDay(now);
  const currentTime = now.getHours() * 60 + now.getMinutes();

  let closest: NextSchedule | null = null;

  for (const schedule of schedules) {
    if (!schedule.enabled) continue;
    const [hours, minutes] = schedule.notification_time.split(':').map(Number);
    const scheduleMinutes = hours * 60 + minutes;

    const notifyDay = schedule.notify_day_before
      ? (schedule.day_of_week + 6) % 7
      : schedule.day_of_week;
    let daysUntil = notifyDay - currentDay;
    if (daysUntil < 0 || (daysUntil === 0 && scheduleMinutes <= currentTime)) {
      daysUntil += 7;
    }

    const minutesUntil = daysUntil === 0 ? scheduleMinutes - currentTime : scheduleMinutes;

    if (
      !closest ||
      daysUntil < closest.daysUntil ||
      (daysUntil === closest.daysUntil && minutesUntil < closest.minutesUntil)
    ) {
      closest = { schedule, notifyDay, daysUntil, minutesUntil };
    }
  }

  return closest;
}
