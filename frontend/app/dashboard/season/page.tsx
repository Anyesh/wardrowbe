'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';
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

const DONE_KEY = 'wardrowbe.seasonSwapDone';

function readDone(season: string): Set<string> {
  try {
    const saved = JSON.parse(window.localStorage.getItem(DONE_KEY) || '{}');
    return new Set(saved.season === season ? saved.ids : []);
  } catch {
    return new Set();
  }
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
  const { data, isLoading, isError } = useSeasonSwap();
  const key = data ? `${data.current_season}-${data.upcoming_season}` : '';
  const [done, setDone] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (key) setDone(readDone(key));
  }, [key]);

  const toggle = (id: string) =>
    setDone((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        window.localStorage.setItem(DONE_KEY, JSON.stringify({ season: key, ids: Array.from(next) }));
      } catch {
        // Not remembered in private mode; the list still works for this visit.
      }
      return next;
    });

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
