'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { List as ListIcon, CalendarDays, Plus, Search } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { OutfitCard } from '@/components/outfits/outfit-card';
import { OutfitCalendar } from '@/components/outfit-calendar';
import {
  useCalendarOutfits,
  useOutfits,
  type Outfit,
  type OutfitFilters,
} from '@/lib/hooks/use-outfits';
import { useI18n } from '@/lib/i18n';
import { cn } from '@/lib/utils';

interface MonthRef {
  year: number;
  month: number;
}

function currentMonthRef(): MonthRef {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

function formatDateKey(y: number, m: number, d: number): string {
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function formatMonthParam(ref: MonthRef): string {
  return `${ref.year}-${String(ref.month).padStart(2, '0')}`;
}

function parseMonthParam(val: string | null): MonthRef | null {
  if (!val) return null;
  const [y, m] = val.split('-').map(Number);
  if (!y || !m || m < 1 || m > 12) return null;
  return { year: y, month: m };
}

function shiftMonth(ref: MonthRef, delta: number): MonthRef {
  const d = new Date(ref.year, ref.month - 1 + delta, 1);
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function outfitDateSet(outfits: Outfit[]): Set<string> {
  const set = new Set<string>();
  for (const o of outfits) {
    if (o.scheduled_for) set.add(o.scheduled_for);
  }
  return set;
}

function outfitsByDate(outfits: Outfit[]): Map<string, Outfit[]> {
  const map = new Map<string, Outfit[]>();
  for (const o of outfits) {
    if (!o.scheduled_for) continue;
    const arr = map.get(o.scheduled_for) ?? [];
    arr.push(o);
    map.set(o.scheduled_for, arr);
  }
  return map;
}

type FilterChip =
  | 'all'
  | 'my-looks'
  | 'worn'
  | 'pairings'
  | 'replacements'
  | 'ai';

type ViewMode = 'list' | 'calendar';

const CHIP_ORDER: FilterChip[] = [
  'all',
  'my-looks',
  'worn',
  'pairings',
  'replacements',
  'ai',
];

function useChipLabels(): Record<FilterChip, string> {
  const { t } = useI18n();
  return useMemo(() => ({
    all: t('outfits.tab.all'),
    'my-looks': t('outfits.tab.myLooks'),
    worn: t('outfits.tab.worn'),
    pairings: t('outfits.tab.pairings'),
    replacements: t('outfits.tab.replacements'),
    ai: t('outfits.tab.ai'),
  }), [t]);
}

function chipToFilters(chip: FilterChip, search: string): OutfitFilters {
  const filters: OutfitFilters = {};
  if (search) filters.search = search;
  switch (chip) {
    case 'my-looks':
      filters.is_lookbook = true;
      return filters;
    case 'worn':
      filters.is_lookbook = false;
      filters.status = 'accepted';
      return filters;
    case 'pairings':
      filters.has_source_item = true;
      return filters;
    case 'replacements':
      filters.is_replacement = true;
      return filters;
    case 'ai':
      filters.source = 'scheduled,on_demand';
      return filters;
    case 'all':
    default:
      return filters;
  }
}

function useEmptyMessages(): Record<FilterChip, string> {
  const { t } = useI18n();
  return useMemo(() => ({
    all: t('outfits.empty.all'),
    'my-looks': t('outfits.empty.myLooks'),
    worn: t('outfits.empty.worn'),
    pairings: t('outfits.empty.pairings'),
    replacements: t('outfits.empty.replacements'),
    ai: t('outfits.empty.ai'),
  }), [t]);
}

function OutfitsPageContent() {
  const { t } = useI18n();
  const CHIP_LABELS = useChipLabels();
  const EMPTY_MESSAGES = useEmptyMessages();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawFilter = (searchParams.get('filter') as FilterChip) || 'all';
  const urlView: ViewMode = searchParams.get('view') === 'calendar' ? 'calendar' : 'list';
  const urlFilter: FilterChip =
    urlView === 'calendar' && rawFilter === 'my-looks' ? 'all' : rawFilter;
  const chip: FilterChip = urlFilter;
  const view: ViewMode = urlView;
  const urlMonth = parseMonthParam(searchParams.get('month'));

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [defaultChecked, setDefaultChecked] = useState(false);
  const [monthRef, setMonthRef] = useState<MonthRef>(urlMonth ?? currentMonthRef());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  useEffect(() => {
    if (urlMonth && (urlMonth.year !== monthRef.year || urlMonth.month !== monthRef.month)) {
      setMonthRef(urlMonth);
    }
  }, [urlMonth, monthRef.year, monthRef.month]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const filters = useMemo(
    () => chipToFilters(chip, debouncedSearch),
    [chip, debouncedSearch],
  );

  const listQuery = useOutfits(filters, page, 24);

  const calendarQuery = useCalendarOutfits(
    monthRef.year,
    monthRef.month,
    view === 'calendar' ? filters : {},
  );

  const lookbookProbe = useOutfits({ is_lookbook: true }, 1, 1);

  useEffect(() => {
    if (defaultChecked) return;
    if (urlFilter !== 'all' || urlView === 'calendar') {
      setDefaultChecked(true);
      return;
    }
    if (lookbookProbe.data) {
      if (lookbookProbe.data.total === 0) {
        const params = new URLSearchParams(searchParams.toString());
        params.set('filter', 'my-looks');
        router.replace(`/dashboard/outfits?${params.toString()}`);
      }
      setDefaultChecked(true);
    }
  }, [defaultChecked, lookbookProbe.data, urlFilter, urlView, searchParams, router]);

  const updateQuery = useCallback(
    (next: {
      filter?: FilterChip;
      view?: ViewMode;
      month?: MonthRef | null;
    }) => {
      const params = new URLSearchParams(searchParams.toString());

      if ('filter' in next) {
        if (!next.filter || next.filter === 'all') {
          params.delete('filter');
        } else {
          params.set('filter', next.filter);
        }
      }

      if ('view' in next) {
        if (!next.view || next.view === 'list') {
          params.delete('view');
        } else {
          params.set('view', next.view);
        }
      }

      if ('month' in next) {
        if (!next.month) {
          params.delete('month');
        } else {
          params.set('month', formatMonthParam(next.month));
        }
      }

      router.replace(
        `/dashboard/outfits${params.toString() ? `?${params}` : ''}`,
      );
    },
    [router, searchParams],
  );

  const handleChipClick = (next: FilterChip) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next === 'all') {
      params.delete('filter');
    } else {
      params.set('filter', next);
    }
    setPage(1);
    setSelectedDate(null);
    router.replace(
      `/dashboard/outfits${params.toString() ? `?${params}` : ''}`,
    );
  };

  const handleViewChange = (next: ViewMode) => {
    setSelectedDate(null);
    const params = new URLSearchParams(searchParams.toString());
    if (next === 'calendar') {
      params.set('view', 'calendar');
      if (params.get('filter') === 'my-looks') {
        params.delete('filter');
      }
    } else {
      params.delete('view');
    }
    router.replace(
      `/dashboard/outfits${params.toString() ? `?${params}` : ''}`,
    );
  };

  const handleMonthChange = (year: number, month: number) => {
    const nextRef = { year, month };
    setMonthRef(nextRef);
    setSelectedDate(null);
    updateQuery({ month: nextRef });
  };

  const handleShiftMonth = (delta: number) => {
    const nextRef = shiftMonth(monthRef, delta);
    setMonthRef(nextRef);
    setSelectedDate(null);
    updateQuery({ month: nextRef });
  };

  const calendarOutfits: Outfit[] = calendarQuery.data?.outfits ?? [];
  const dateSet = useMemo(() => outfitDateSet(calendarOutfits), [calendarOutfits]);
  const dateMap = useMemo(() => outfitsByDate(calendarOutfits), [calendarOutfits]);
  const selectedDayOutfits: Outfit[] = selectedDate
    ? dateMap.get(selectedDate) ?? []
    : [];

  const outfits = listQuery.data?.outfits ?? [];
  const hasMore = listQuery.data?.has_more ?? false;
  const listLoading = listQuery.isLoading;
  const listError = listQuery.isError;
  const calendarLoading = calendarQuery.isLoading;
  const calendarError = calendarQuery.isError;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t('outfits.title')}</h1>
          <p className="text-muted-foreground">{t('outfits.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3">
          <div
            className="inline-flex rounded-full border-2 border-muted overflow-hidden"
            role="group"
            aria-label="View toggle"
          >
            <button
              type="button"
              onClick={() => handleViewChange('list')}
              aria-pressed={view === 'list'}
              className={cn(
                'inline-flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium transition-colors',
                view === 'list'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-background text-muted-foreground hover:text-foreground',
              )}
            >
              <ListIcon className="h-3.5 w-3.5" />
              {t('outfits.list')}
            </button>
            <button
              type="button"
              onClick={() => handleViewChange('calendar')}
              aria-pressed={view === 'calendar'}
              className={cn(
                'inline-flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium transition-colors border-l-2 border-muted',
                view === 'calendar'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-background text-muted-foreground hover:text-foreground',
              )}
            >
              <CalendarDays className="h-3.5 w-3.5" />
              {t('outfits.calendar')}
            </button>
          </div>
          <Button asChild>
            <Link href="/dashboard/outfits/new">
              <Plus className="h-4 w-4 mr-2" />
              {t('outfits.new')}
            </Link>
          </Button>
        </div>
      </div>

      {view === 'list' && (
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex flex-wrap gap-2">
          {CHIP_ORDER.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => handleChipClick(c)}
              className={cn(
                'inline-flex items-center rounded-full border-2 px-4 py-1.5 text-sm font-medium transition-all',
                chip === c
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-muted bg-background hover:border-muted-foreground/50',
              )}
            >
              {CHIP_LABELS[c]}
            </button>
          ))}
        </div>

        {chip === 'my-looks' && (
          <div className="relative ml-auto min-w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t('outfits.searchPlaceholder')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 h-9"
            />
          </div>
        )}

        {listQuery.data && (
          <Badge variant="outline" className="ml-auto">
            {listQuery.data.total} {t('outfits.totalCount')}
          </Badge>
        )}
      </div>
      )}

      {view === 'list' ? (
        <>
          {listError ? (
            <div className="text-center py-8 text-destructive">{t('outfits.loadFailed')}</div>
          ) : listLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="aspect-[5/4] rounded-lg" />
              ))}
            </div>
          ) : outfits.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
              <p className="text-muted-foreground mb-6 max-w-sm">{EMPTY_MESSAGES[chip]}</p>
              {chip === 'my-looks' && (
                <Button asChild>
                  <Link href="/dashboard/outfits/new">
                    <Plus className="h-4 w-4 mr-2" />
                    {t('outfits.new')}
                  </Link>
                </Button>
              )}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {outfits.map((outfit) => (
                  <OutfitCard key={outfit.id} outfit={outfit} />
                ))}
              </div>
              {hasMore && (
                <div className="flex justify-center pt-4">
                  <Button variant="outline" onClick={() => setPage((p) => p + 1)}>
                    {t('common.loadMore')}
                  </Button>
                </div>
              )}
            </>
          )}
        </>
      ) : (
        <div className="grid lg:grid-cols-[360px_1fr] gap-6">
          <Card className="h-fit">
            <CardContent className="p-4">
              {calendarLoading ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between mb-4">
                    <Skeleton className="h-8 w-8" />
                    <Skeleton className="h-6 w-32" />
                    <Skeleton className="h-8 w-8" />
                  </div>
                  <div className="grid grid-cols-7 gap-1">
                    {Array.from({ length: 35 }).map((_, i) => (
                      <Skeleton key={i} className="h-10 w-full rounded-md" />
                    ))}
                  </div>
                </div>
              ) : (
                <OutfitCalendar
                  year={monthRef.year}
                  month={monthRef.month}
                  outfits={calendarOutfits}
                  selectedDate={selectedDate ? parseYmd(selectedDate) : null}
                  onSelectDate={(d: Date) =>
                    setSelectedDate(formatDateKey(d.getFullYear(), d.getMonth() + 1, d.getDate()))
                  }
                  onMonthChange={handleMonthChange}
                />
              )}
            </CardContent>
          </Card>

          <div className="space-y-4">
            {calendarError ? (
              <div className="text-center py-8 text-destructive">{t('outfits.loadFailed')}</div>
            ) : calendarLoading ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="aspect-[5/4] rounded-lg" />
                ))}
              </div>
            ) : selectedDate && selectedDayOutfits.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
                <CalendarDays className="h-8 w-8 text-muted-foreground mb-2" />
                <p className="text-sm text-muted-foreground">
                  {t('outfits.noOnDay')}
                </p>
              </div>
            ) : (
              <>
                {selectedDate && (
                  <div className="border-b pb-3">
                    <h2 className="text-lg font-semibold">
                      {formatReadableDate(selectedDate)}
                    </h2>
                    <p className="text-sm text-muted-foreground">
                      {selectedDayOutfits.length} {t('outfits.counts')}
                    </p>
                  </div>
                )}
                {!selectedDate && (
                  <p className="text-sm text-muted-foreground">
                    {calendarOutfits.length} {t('outfits.counts')} {t('outfits.thisMonth')}
                  </p>
                )}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {(selectedDate ? selectedDayOutfits : calendarOutfits).map((outfit) => (
                    <OutfitCard key={outfit.id} outfit={outfit} />
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function parseYmd(dateKey: string): Date {
  const [y, m, d] = dateKey.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function formatReadableDate(dateKey: string): string {
  return parseYmd(dateKey).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

export default function OutfitsPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-6">
          <Skeleton className="h-10 w-48" />
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="aspect-[5/4] rounded-lg" />
            ))}
          </div>
        </div>
      }
    >
      <OutfitsPageContent />
    </Suspense>
  );
}