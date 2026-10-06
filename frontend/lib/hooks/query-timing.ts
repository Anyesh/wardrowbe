const MINUTE = 60 * 1000;

export const DEFAULT_STALE_TIME = MINUTE;
export const SLOW_STALE_TIME = 5 * MINUTE;
export const WEATHER_STALE_TIME = 15 * MINUTE;

const PROCESSING_POLL_INTERVAL = 5 * 1000;
const IDLE_POLL_INTERVAL = 30 * 1000;

export function processingPollInterval(processing: boolean) {
  return processing ? PROCESSING_POLL_INTERVAL : IDLE_POLL_INTERVAL;
}
