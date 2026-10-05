import type { Schedule } from '@/lib/hooks/use-notifications';
import { getWallClockInTimezone } from '@/lib/utils';

export interface NextSchedule {
  schedule: Schedule;
  daysUntil: number;
  minutesUntil: number;
}

export function findNextSchedule(schedules: Schedule[], timezone: string): NextSchedule | null {
  const now = getWallClockInTimezone(timezone);
  const currentDay = now.getDay();
  const currentTime = now.getHours() * 60 + now.getMinutes();

  let closest: NextSchedule | null = null;

  for (const schedule of schedules) {
    if (!schedule.enabled) continue;
    const [hours, minutes] = schedule.notification_time.split(':').map(Number);
    const scheduleMinutes = hours * 60 + minutes;

    let daysUntil = schedule.day_of_week - currentDay;
    if (daysUntil < 0 || (daysUntil === 0 && scheduleMinutes <= currentTime)) {
      daysUntil += 7;
    }

    const minutesUntil = daysUntil === 0 ? scheduleMinutes - currentTime : scheduleMinutes;

    if (
      !closest ||
      daysUntil < closest.daysUntil ||
      (daysUntil === closest.daysUntil && minutesUntil < closest.minutesUntil)
    ) {
      closest = { schedule, daysUntil, minutesUntil };
    }
  }

  return closest;
}
