'use client';

import { useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Gift, Heart, Recycle, Tag } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getErrorMessage } from '@/lib/api';
import { useDeclutter, useKeepItem, type DeclutterCandidate } from '@/lib/hooks/use-declutter';
import { useArchiveItem } from '@/lib/hooks/use-items';
import { useTypeLabel } from '@/lib/hooks/use-translated-constants';
import { queryKeys } from '@/lib/hooks/query-keys';
import { useQueryClient } from '@tanstack/react-query';

const WINDOWS = [3, 6, 12, 24] as const;

function CandidateCard({ candidate, months }: { candidate: DeclutterCandidate; months: number }) {
  const t = useTranslations('declutter');
  const locale = useLocale();
  const typeLabel = useTypeLabel();
  const keep = useKeepItem();
  const archive = useArchiveItem();
  const queryClient = useQueryClient();
  const { item } = candidate;
  const busy = keep.isPending || archive.isPending;
  const label = item.name || typeLabel(item.type);

  const giveAway = (reason: 'donated' | 'sold') => {
    archive.mutate(
      { id: item.id, reason },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: queryKeys.declutterAll });
          toast.success(reason === 'donated' ? t('toast.donated', { name: label }) : t('toast.sold', { name: label }));
        },
        onError: (error) => toast.error(getErrorMessage(error, t('toast.error'))),
      }
    );
  };

  return (
    <Card>
      <CardContent className="flex gap-4 pt-6">
        <Link
          href={`/dashboard/wardrobe?item=${item.id}`}
          className="relative h-24 w-24 shrink-0 overflow-hidden rounded-md bg-muted"
        >
          {item.thumbnail_url && (
            <Image src={item.thumbnail_url} alt={label} fill className="object-cover" sizes="96px" />
          )}
        </Link>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="truncate font-medium">{label}</div>
          <div className="flex flex-wrap gap-1">
            <Badge variant={candidate.reason === 'never_worn' ? 'destructive' : 'secondary'}>
              {candidate.reason === 'never_worn'
                ? t('reason.neverWorn', { days: candidate.idle_days })
                : t('reason.notWorn', { days: candidate.idle_days })}
            </Badge>
            {item.purchase_price != null && Number(item.purchase_price) > 0 && (
              <Badge variant="outline">
                {new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' }).format(Number(item.purchase_price))}
              </Badge>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() =>
                keep.mutate(
                  { id: item.id, months },
                  {
                    onSuccess: () => toast.success(t('toast.kept', { name: label, months })),
                    onError: (error) => toast.error(getErrorMessage(error, t('toast.error'))),
                  }
                )
              }
            >
              <Heart className="mr-1 h-3 w-3" />
              {t('actions.keep')}
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => giveAway('donated')}>
              <Gift className="mr-1 h-3 w-3" />
              {t('actions.donate')}
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => giveAway('sold')}>
              <Tag className="mr-1 h-3 w-3" />
              {t('actions.sell')}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function DeclutterPage() {
  const t = useTranslations('declutter');
  const locale = useLocale();
  const [months, setMonths] = useState(6);
  const { data, isLoading, isError } = useDeclutter(months);

  const value = data ? Number(data.idle_value) : 0;
  const money = new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Recycle className="h-6 w-6" />
            {t('title')}
          </h1>
          <p className="text-muted-foreground">{t('subtitle')}</p>
        </div>
        <Select value={String(months)} onValueChange={(v) => setMonths(Number(v))}>
          <SelectTrigger className="w-56" aria-label={t('window')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {WINDOWS.map((m) => (
              <SelectItem key={m} value={String(m)}>
                {t('windowOption', { months: m })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {isError && <p className="text-sm text-destructive">{t('toast.error')}</p>}

      {data && (
        <>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                {t('summary', { count: data.candidates.length, total: data.total_items })}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              {value > 0 ? t('idleValue', { value: money.format(value) }) : t('hint')}
            </CardContent>
          </Card>

          {data.candidates.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">{t('empty')}</p>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {data.candidates.map((c) => (
                <CandidateCard key={c.item.id} candidate={c} months={months} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
