'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';
import { useSession } from 'next-auth/react';
import { useTranslations } from 'next-intl';
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpFromLine,
  CalendarRange,
  CheckCircle2,
  Circle,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useSeasonSwap, type SwapEntry } from '@/lib/hooks/use-season-swap';
import { useSeasonLabel, useTypeLabel } from '@/lib/hooks/use-translated-constants';

// One record per account in this browser, for the current swap only (seasons and year).
function doneKey(userId: string): string {
  return `wardrowbe.seasonSwapDone.${userId}`;
}

function readDone(userId: string, swap: string): Set<string> {
  try {
    const saved = JSON.parse(window.localStorage.getItem(doneKey(userId)) || '{}');
    return new Set(saved.season === swap ? saved.ids : []);
  } catch {
    return new Set();
  }
}

// The year a swap belongs to, taken two months back so a winter swap that runs past New Year
// keeps its ticks.
function swapYear(): number {
  const shifted = new Date();
  shifted.setMonth(shifted.getMonth() - 2);
  return shifted.getFullYear();
}

// Read-modify-write on the stored ids, so a tick made in another tab is not overwritten.
function storeToggle(userId: string, swap: string, id: string, checked: boolean): Set<string> {
  const ids = readDone(userId, swap);
  if (checked) ids.add(id);
  else ids.delete(id);
  try {
    window.localStorage.setItem(doneKey(userId), JSON.stringify({ season: swap, ids: Array.from(ids) }));
  } catch {
    // Not remembered in private mode; the list still works for this visit.
  }
  return ids;
}

function Column({
  title,
  description,
  icon: Icon,
  entries,
  done,
  onToggle,
}: {
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  entries: SwapEntry[];
  done: Set<string>;
  onToggle: (id: string) => void;
}) {
  const t = useTranslations('season');
  const typeLabel = useTypeLabel();
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="h-4 w-4" />
          {title}
          <span className="text-sm font-normal text-muted-foreground">({entries.length})</span>
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('nothing')}</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {entries.map(({ item, reason }) => {
              const checked = done.has(item.id);
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onToggle(item.id)}
                  aria-pressed={checked}
                  className={`rounded-lg border p-2 text-left transition ${checked ? 'opacity-50' : ''}`}
                >
                  <div className="relative mb-2 aspect-square overflow-hidden rounded-md bg-muted">
                    {item.thumbnail_url && (
                      <Image
                        src={item.thumbnail_url}
                        alt={item.name || typeLabel(item.type)}
                        fill
                        className="object-cover"
                        sizes="160px"
                      />
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    {checked ? (
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />
                    ) : (
                      <Circle className="h-4 w-4 shrink-0 text-muted-foreground" />
                    )}
                    <span className="truncate">{item.name || typeLabel(item.type)}</span>
                  </div>
                  {reason === 'last_year' && (
                    <div className="mt-1 text-[11px] text-muted-foreground">{t('lastYear')}</div>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function SeasonSwapPage() {
  const t = useTranslations('season');
  const seasonLabel = useSeasonLabel();
  const { data: session } = useSession();
  const userId = session?.user?.id ?? '';
  const { data, isLoading, isError } = useSeasonSwap();
  // The year keeps next autumn's swap from opening with this autumn's ticks.
  const key = data ? `${swapYear()}-${data.current_season}-${data.upcoming_season}` : '';
  const [done, setDone] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!key) return;
    setDone(readDone(userId, key));
    // Ticks made in another tab show up here too.
    const onStorage = (event: StorageEvent) => {
      if (event.key === doneKey(userId)) setDone(readDone(userId, key));
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [key, userId]);

  const toggle = (id: string) => setDone(storeToggle(userId, key, id, !done.has(id)));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <CalendarRange className="h-6 w-6" />
          {t('title')}
        </h1>
        <p className="text-muted-foreground">{t('subtitle')}</p>
      </div>

      {isLoading && <Skeleton className="h-40 w-full" />}
      {isError && <p className="text-sm text-destructive">{t('error')}</p>}

      {data && (
        <>
          <Card>
            <CardContent className="flex flex-wrap items-center gap-3 pt-6 text-sm">
              <span className="font-medium">{seasonLabel(data.current_season)}</span>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium">{seasonLabel(data.upcoming_season)}</span>
              <span className="text-muted-foreground">
                {data.current_season === data.upcoming_season
                  ? t('sameSeason')
                  : t('stays', { count: data.stays })}
              </span>
            </CardContent>
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <Column
              title={t('putAway.title')}
              description={t('putAway.description')}
              icon={ArrowDownToLine}
              entries={data.put_away}
              done={done}
              onToggle={toggle}
            />
            <Column
              title={t('bringOut.title')}
              description={t('bringOut.description')}
              icon={ArrowUpFromLine}
              entries={data.bring_out}
              done={done}
              onToggle={toggle}
            />
          </div>
          <p className="text-xs text-muted-foreground">{t('hint')}</p>
        </>
      )}
    </div>
  );
}
