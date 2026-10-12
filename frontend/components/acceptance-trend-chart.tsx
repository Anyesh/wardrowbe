'use client';

import { useLocale, useTranslations } from 'next-intl';
import type { AcceptanceRateTrend } from '@/lib/hooks/use-analytics';
import { formatDate } from '@/lib/utils';

const PERIOD_OPTIONS: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };

export function AcceptanceTrendChart({ data }: { data: AcceptanceRateTrend[] }) {
  const t = useTranslations('analytics');
  const locale = useLocale();
  const maxTotal = Math.max(...data.map((d) => d.total), 1);

  return (
    <div className="space-y-2">
      {data.map((week) => (
        <div key={week.period_start} className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground w-16 flex-shrink-0">{formatDate(week.period_start, locale, PERIOD_OPTIONS)}</span>
          <div className="flex-1 flex items-center gap-2">
            <div
              className="h-4 bg-primary/20 rounded relative overflow-hidden"
              style={{ width: `${(week.total / maxTotal) * 100}%`, minWidth: week.total > 0 ? '20px' : '0' }}
            >
              <div
                className="absolute inset-y-0 left-0 bg-primary rounded"
                style={{ width: `${week.rate}%` }}
              />
            </div>
            {week.total > 0 && (
              <span className="text-xs text-muted-foreground">{t('percent', { value: week.rate.toFixed(0) })}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
