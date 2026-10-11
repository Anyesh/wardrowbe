'use client';

import { Bot, Calendar, Edit3, Zap } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Badge } from '@/components/ui/badge';
import type { OutfitSource } from '@/lib/hooks/use-outfits';

export function SourceBadge({ source }: { source: OutfitSource }) {
  const t = useTranslations('constants.outfitSources');
  const config: Record<OutfitSource, { icon: typeof Calendar; label: string; className: string }> = {
    scheduled: {
      icon: Calendar,
      label: t('scheduled'),
      className: 'bg-primary/10 text-primary border-primary/20',
    },
    on_demand: {
      icon: Zap,
      label: t('onDemand'),
      className: 'bg-orange-500/10 text-orange-600 border-orange-500/20',
    },
    manual: {
      icon: Edit3,
      label: t('manual'),
      className: 'bg-purple-500/10 text-purple-600 border-purple-500/20',
    },
    pairing: {
      icon: Zap,
      label: t('pairing'),
      className: 'bg-violet-500/10 text-violet-600 border-violet-500/20',
    },
    external: {
      icon: Bot,
      label: t('external'),
      className: 'bg-teal-500/10 text-teal-600 border-teal-500/20',
    },
  };

  const { icon: Icon, label, className } = config[source];

  return (
    <Badge variant="outline" className={className}>
      <Icon className="h-3 w-3 mr-1" />
      {label}
    </Badge>
  );
}
