'use client';

import { useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { AlertTriangle, CheckCircle2, Circle, CloudRain, Loader2, Luggage, Thermometer } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ApiError, getErrorMessage } from '@/lib/api';
import { usePackingPlan, type PackingPlan } from '@/lib/hooks/use-packing';
import {
  useOccasionOptions,
  useRoleLabel,
  useSeasonLabel,
  useTypeLabel,
  useWeatherConditionLabel,
} from '@/lib/hooks/use-translated-constants';
import { formatDateKey, formatShortDate } from '@/lib/utils';

function addDays(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return formatDateKey(date);
}

function PlanView({ plan, laundry }: { plan: PackingPlan; laundry: boolean }) {
  const t = useTranslations('packing');
  const locale = useLocale();
  const roleLabel = useRoleLabel();
  const typeLabel = useTypeLabel();
  const seasonLabel = useSeasonLabel();
  const conditionLabel = useWeatherConditionLabel();
  const [packed, setPacked] = useState<Set<string>>(new Set());

  const total = plan.groups.reduce((sum, g) => sum + g.items.length, 0);
  const changes = laundry ? Math.min(plan.days, 4) + 1 : plan.days + 1;

  const toggle = (id: string) =>
    setPacked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{plan.destination}</CardTitle>
          <CardDescription>
            {t('summary.dates', {
              start: formatShortDate(plan.start_date, locale),
              end: formatShortDate(plan.end_date, locale),
              days: plan.days,
            })}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary" className="gap-1">
              <Thermometer className="h-3 w-3" />
              {t('summary.temperature', { min: Math.round(plan.temp_min), max: Math.round(plan.temp_max) })}
            </Badge>
            <Badge variant="secondary" className="gap-1">
              <CloudRain className="h-3 w-3" />
              {t('summary.rainDays', { count: plan.rain_days })}
            </Badge>
            <Badge variant="outline">{seasonLabel(plan.season)}</Badge>
            {plan.estimated && <Badge variant="outline">{t('summary.estimated')}</Badge>}
          </div>
          {plan.estimated && (
            <p className="text-sm text-muted-foreground">{t('summary.estimatedHelp')}</p>
          )}
          {plan.forecast.length > 0 && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {plan.forecast.map((day) => (
                <div key={day.date} className="min-w-[88px] rounded-lg border p-2 text-center text-xs">
                  <div className="font-medium">{formatShortDate(day.date, locale)}</div>
                  <div className="text-muted-foreground">{conditionLabel(day.condition)}</div>
                  <div>
                    {t('summary.dayRange', { min: Math.round(day.temp_min), max: Math.round(day.temp_max) })}
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="text-sm">
            {t('summary.progress', { packed: packed.size, total })} · {t('summary.underwear', { count: changes })}
          </p>
        </CardContent>
      </Card>

      {plan.missing_roles.length > 0 && (
        <Card className="border-amber-500/50">
          <CardContent className="flex items-start gap-3 pt-6 text-sm">
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
            <div>
              {t('missing', { roles: plan.missing_roles.map((r) => roleLabel(r)).join(', ') })}{' '}
              <Link href="/dashboard/wardrobe" className="underline">
                {t('addItems')}
              </Link>
            </div>
          </CardContent>
        </Card>
      )}

      {plan.groups.map((group) => (
        <Card key={group.role}>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              {roleLabel(group.role)}{' '}
              <span className="text-sm font-normal text-muted-foreground">
                {t('groupCount', { found: group.items.length, needed: group.needed })}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {group.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('noneSuitable')}</p>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {group.items.map((item) => {
                  const done = packed.has(item.id);
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => toggle(item.id)}
                      aria-pressed={done}
                      className={`rounded-lg border p-2 text-left transition ${done ? 'opacity-50' : ''}`}
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
                      <div className="flex items-center gap-2">
                        {done ? (
                          <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" aria-label={t('packedLabel')} />
                        ) : (
                          <Circle className="h-4 w-4 shrink-0 text-muted-foreground" />
                        )}
                        <span className="truncate text-sm">{item.name || typeLabel(item.type)}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function PackingPage() {
  const t = useTranslations('packing');
  const occasions = useOccasionOptions(['travel']);
  const plan = usePackingPlan();
  const [destination, setDestination] = useState('');
  const [startDate, setStartDate] = useState(addDays(1));
  const [endDate, setEndDate] = useState(addDays(4));
  const [occasion, setOccasion] = useState('travel');
  const [laundry, setLaundry] = useState(false);

  const errorText = (error: unknown) => {
    if (error instanceof ApiError && error.status === 404) return t('notFound');
    if (error instanceof ApiError && (error.status === 400 || error.status === 422)) return t('invalidDates');
    return getErrorMessage(error, t('error'));
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!destination.trim()) return;
    plan.mutate({ destination: destination.trim(), start_date: startDate, end_date: endDate, occasion, laundry });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <Luggage className="h-6 w-6" />
          {t('title')}
        </h1>
        <p className="text-muted-foreground">{t('subtitle')}</p>
      </div>

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="destination">{t('form.destination')}</Label>
              <Input
                id="destination"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder={t('form.destinationPlaceholder')}
                maxLength={200}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="start">{t('form.start')}</Label>
              <Input id="start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="end">{t('form.end')}</Label>
              <Input
                id="end"
                type="date"
                value={endDate}
                min={startDate}
                onChange={(e) => setEndDate(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>{t('form.occasion')}</Label>
              <Select value={occasion} onValueChange={setOccasion}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {occasions.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <Label htmlFor="laundry">{t('form.laundry')}</Label>
                <p className="text-xs text-muted-foreground">{t('form.laundryHelp')}</p>
              </div>
              <Switch id="laundry" checked={laundry} onCheckedChange={setLaundry} />
            </div>
            <div className="md:col-span-2">
              <Button type="submit" disabled={plan.isPending || !destination.trim()} className="w-full md:w-auto">
                {plan.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('form.submit')}
              </Button>
            </div>
          </form>
          {plan.isError && (
            <p className="mt-4 text-sm text-destructive">{errorText(plan.error)}</p>
          )}
        </CardContent>
      </Card>

      {plan.data && <PlanView key={`${plan.data.destination}-${plan.data.start_date}`} plan={plan.data} laundry={plan.variables?.laundry ?? false} />}
    </div>
  );
}
