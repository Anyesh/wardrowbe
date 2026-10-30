'use client';

import { Clock, Eye, SkipForward, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { OUTFIT_STATUSES, type OutfitStatus } from '@/lib/types';
import { cn } from '@/lib/utils';

const STATUS_ICONS: Record<OutfitStatus, { icon: typeof Clock; className: string }> = {
  pending: { icon: Clock, className: 'text-muted-foreground' },
  sent: { icon: Clock, className: 'text-muted-foreground' },
  viewed: { icon: Eye, className: 'text-blue-500' },
  accepted: { icon: ThumbsUp, className: 'text-green-500' },
  rejected: { icon: ThumbsDown, className: 'text-red-500' },
  skipped: { icon: SkipForward, className: 'text-muted-foreground' },
  expired: { icon: Clock, className: 'text-orange-500' },
};

const ALL = 'all';

export function OutfitStatusIcon({ status }: { status: OutfitStatus }) {
  const t = useTranslations('history.status');
  const { icon: Icon, className } = STATUS_ICONS[status];
  const label = t(status);

  return (
    <span role="img" aria-label={label} title={label}>
      <Icon className={cn('h-4 w-4', className)} aria-hidden="true" />
    </span>
  );
}

export function OutfitStatusFilter({
  value,
  onChange,
}: {
  value: OutfitStatus | undefined;
  onChange: (status: OutfitStatus | undefined) => void;
}) {
  const t = useTranslations('history');

  return (
    <Select
      value={value ?? ALL}
      onValueChange={(next) => onChange(OUTFIT_STATUSES.find((s) => s === next))}
    >
      <SelectTrigger className="w-[150px]">
        <SelectValue placeholder={t('filters.allStatus')} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{t('filters.allStatus')}</SelectItem>
        {OUTFIT_STATUSES.map((status) => (
          <SelectItem key={status} value={status}>
            {t(`status.${status}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
