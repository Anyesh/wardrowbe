'use client';

import { useState, useEffect, Suspense } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { useTranslations } from 'next-intl';
import {
  Briefcase,
  Shirt,
  Heart,
  Dumbbell,
  TreePine,
  Sparkles,
  RefreshCw,
  ThumbsUp,
  ThumbsDown,
  Cloud,
  Sun,
  CloudRain,
  Loader2,
  AlertCircle,
  Thermometer,
  Droplets,
  ChevronDown,
  MapPin,
  Wind,
  GlassWater,
  Cloudy,
  CloudSun,
  Snowflake,
  CalendarDays,
  CloudLightning,
  Plus,
  X,
  Layers,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { ItemPicker } from '@/components/shared/item-picker';
import { useItem } from '@/lib/hooks/use-items';
import { api, ApiError, setAccessToken } from '@/lib/api';
import { Item, Outfit, SuggestRequest } from '@/lib/types';
import { useOccasions } from '@/lib/hooks/use-translated-constants';
import { useWeather, Weather } from '@/lib/hooks/use-weather';
import { usePreferences } from '@/lib/hooks/use-preferences';
import { cn } from '@/lib/utils';
import { TempUnit, formatTemp, displayValue, toF, toCelsius } from '@/lib/temperature';

type Translator = (key: string, values?: Record<string, string | number>) => string;

const OVERRIDE_CONDITION_KEYS: Record<string, string> = {
  sunny: 'clear',
  cloudy: 'cloudy',
  rainy: 'rain',
};

// Map occasion values to icons and colors
const OCCASION_CONFIG: Record<string, { icon: React.ReactNode; color: string }> = {
  casual: { icon: <Shirt className="h-4 w-4" />, color: 'hover:border-blue-400 hover:bg-blue-50 data-[selected=true]:border-blue-500 data-[selected=true]:bg-blue-50 data-[selected=true]:text-blue-700' },
  office: { icon: <Briefcase className="h-4 w-4" />, color: 'hover:border-slate-400 hover:bg-slate-50 data-[selected=true]:border-slate-500 data-[selected=true]:bg-slate-50 data-[selected=true]:text-slate-700' },
  formal: { icon: <GlassWater className="h-4 w-4" />, color: 'hover:border-purple-400 hover:bg-purple-50 data-[selected=true]:border-purple-500 data-[selected=true]:bg-purple-50 data-[selected=true]:text-purple-700' },
  date: { icon: <Heart className="h-4 w-4" />, color: 'hover:border-rose-400 hover:bg-rose-50 data-[selected=true]:border-rose-500 data-[selected=true]:bg-rose-50 data-[selected=true]:text-rose-700' },
  sporty: { icon: <Dumbbell className="h-4 w-4" />, color: 'hover:border-orange-400 hover:bg-orange-50 data-[selected=true]:border-orange-500 data-[selected=true]:bg-orange-50 data-[selected=true]:text-orange-700' },
  outdoor: { icon: <TreePine className="h-4 w-4" />, color: 'hover:border-green-400 hover:bg-green-50 data-[selected=true]:border-green-500 data-[selected=true]:bg-green-50 data-[selected=true]:text-green-700' },
};

// Weather condition to icon mapping
function getWeatherIcon(condition: string, isDay: boolean) {
  const c = condition.toLowerCase();
  if (c.includes('rain') || c.includes('drizzle')) return <CloudRain className="h-8 w-8" />;
  if (c.includes('snow')) return <Snowflake className="h-8 w-8" />;
  if (c.includes('thunder') || c.includes('storm')) return <CloudLightning className="h-8 w-8" />;
  if (c.includes('cloud') && c.includes('part')) return <CloudSun className="h-8 w-8" />;
  if (c.includes('cloud') || c.includes('overcast')) return <Cloudy className="h-8 w-8" />;
  return isDay ? <Sun className="h-8 w-8" /> : <Cloud className="h-8 w-8" />;
}

// Get time-based greeting key
function getGreetingKey(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'greeting.morning';
  if (hour < 17) return 'greeting.afternoon';
  return 'greeting.evening';
}

// Get weather-based outfit hint key
function getWeatherHintKey(weather: Weather): string {
  const temp = weather.temperature;
  const condition = weather.condition.toLowerCase();

  if (weather.precipitation_chance > 50) return 'weatherHints.rainy';
  if (temp < 10) return 'weatherHints.cold';
  if (temp < 18) return 'weatherHints.mild';
  if (temp > 28) return 'weatherHints.hot';
  if (condition.includes('wind')) return 'weatherHints.windy';
  return 'weatherHints.nice';
}

interface WeatherOverride {
  temperature: number;
  condition: 'sunny' | 'cloudy' | 'rainy';
}

function WeatherCard({ weather, isLoading, temperatureUnit, t }: { weather?: Weather; isLoading: boolean; temperatureUnit: TempUnit; t: Translator }) {
  if (isLoading) {
    return (
      <Card className="border-muted">
        <CardContent className="p-6">
          <div className="flex items-center gap-4">
            <Skeleton className="h-16 w-16 rounded-full" />
            <div className="space-y-2">
              <Skeleton className="h-8 w-24" />
              <Skeleton className="h-4 w-32" />
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!weather) {
    return (
      <Card className="border-dashed">
        <CardContent className="p-6">
          <div className="flex items-center gap-4">
            <div className="h-14 w-14 rounded-full bg-muted flex items-center justify-center">
              <MapPin className="h-6 w-6 text-muted-foreground" />
            </div>
            <div>
              <p className="font-medium">{t('location.notSet')}</p>
              <p className="text-sm text-muted-foreground">
                {t('location.setDescription')}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="h-14 w-14 rounded-full bg-muted flex items-center justify-center text-foreground">
              {getWeatherIcon(weather.condition, weather.is_day)}
            </div>
            <div>
              <div className="flex items-baseline gap-1">
                <span className="text-4xl font-semibold tracking-tight">{displayValue(weather.temperature, temperatureUnit)}</span>
                <span className="text-lg text-muted-foreground">{temperatureUnit === 'fahrenheit' ? '°F' : '°C'}</span>
              </div>
              <p className="text-sm text-muted-foreground capitalize">{weather.condition}</p>
            </div>
          </div>
          <div className="text-right text-sm text-muted-foreground space-y-1">
            <div className="flex items-center gap-1.5 justify-end">
              <Thermometer className="h-3.5 w-3.5" />
              <span>{t('weather.feelsLike', { temp: displayValue(weather.feels_like, temperatureUnit) })}</span>
            </div>
            <div className="flex items-center gap-1.5 justify-end">
              <Droplets className="h-3.5 w-3.5" />
              <span>{t('weather.rainChance', { chance: weather.precipitation_chance })}</span>
            </div>
            <div className="flex items-center gap-1.5 justify-end">
              <Wind className="h-3.5 w-3.5" />
              <span>{t('weather.windSpeed', { speed: Math.round(weather.wind_speed) })}</span>
            </div>
          </div>
        </div>
        <div className="mt-4 pt-4 border-t">
          <p className="text-sm text-muted-foreground">
            {t(getWeatherHintKey(weather))}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function OccasionChips({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (occasion: string) => void;
}) {
  const occasions = useOccasions();
  return (
    <div className="flex flex-wrap gap-2">
      {occasions.map((occasion) => {
        const config = OCCASION_CONFIG[occasion.value];
        return (
          <button
            key={occasion.value}
            onClick={() => onSelect(occasion.value)}
            data-selected={selected === occasion.value}
            className={cn(
              'inline-flex items-center gap-2 px-4 py-2.5 rounded-full border-2 transition-all',
              'border-muted bg-background',
              config?.color || 'hover:border-primary hover:bg-primary/5',
              'focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary/50'
            )}
          >
            {config?.icon}
            <span className="text-sm font-medium">{occasion.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function WeatherOverrideSection({
  weather,
  onChange,
  temperatureUnit,
  t,
}: {
  weather: WeatherOverride | null;
  onChange: (weather: WeatherOverride | null) => void;
  temperatureUnit: TempUnit;
  t: Translator;
}) {
  const tc = useTranslations('constants.weatherConditions');
  const [isOpen, setIsOpen] = useState(false);
  const conditions = [
    { value: 'sunny', icon: <Sun className="h-4 w-4" /> },
    { value: 'cloudy', icon: <Cloud className="h-4 w-4" /> },
    { value: 'rainy', icon: <CloudRain className="h-4 w-4" /> },
  ] as const;

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ChevronDown className={cn('h-4 w-4 transition-transform', isOpen && 'rotate-180')} />
          <span>{weather ? t('weatherOverride.active') : t('weatherOverride.overrideWeather')}</span>
          {weather && (
            <Badge variant="secondary" className="text-xs">
              {tc(OVERRIDE_CONDITION_KEYS[weather.condition])} {formatTemp(weather.temperature, temperatureUnit)}
            </Badge>
          )}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-4">
        <div className="space-y-4 p-4 rounded-lg bg-muted/50">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t('weatherOverride.condition')}</span>
            {weather && (
              <Button variant="ghost" size="sm" onClick={() => onChange(null)}>
                {t('weatherOverride.reset')}
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            {conditions.map((c) => (
              <button
                key={c.value}
                onClick={() =>
                  onChange({
                    temperature: weather?.temperature ?? 20,
                    condition: c.value,
                  })
                }
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg border transition-all',
                  weather?.condition === c.value
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-muted bg-background hover:border-primary/50'
                )}
              >
                {c.icon}
                <span className="text-sm">{tc(OVERRIDE_CONDITION_KEYS[c.value])}</span>
              </button>
            ))}
          </div>
          {weather && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">{t('weatherOverride.temperature')}</span>
              <input
                type="range"
                min={temperatureUnit === 'fahrenheit' ? 14 : -10}
                max={temperatureUnit === 'fahrenheit' ? 104 : 40}
                value={temperatureUnit === 'fahrenheit' ? Math.round(toF(weather.temperature)) : weather.temperature}
                onChange={(e) => {
                  const raw = parseInt(e.target.value);
                  onChange({ ...weather, temperature: temperatureUnit === 'fahrenheit' ? Math.round(toCelsius(raw)) : raw });
                }}
                className="flex-1 accent-primary"
              />
              <span className="text-sm font-medium w-14 text-right">{formatTemp(weather.temperature, temperatureUnit)}</span>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function OutfitCard({
  outfit,
  baseItemId,
  temperatureUnit,
  t,
  onAccept,
  onReject,
  showActions = true,
  badgeLabel,
}: {
  outfit: Outfit;
  baseItemId?: string;
  temperatureUnit: TempUnit;
  t: Translator;
  onAccept?: () => void;
  onReject?: () => void;
  showActions?: boolean;
  badgeLabel?: string;
}) {
  return (
    <Card className="overflow-hidden flex flex-col h-full">
      <div className="bg-gradient-to-r from-primary/10 to-primary/5 p-4 border-b">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Sparkles className="h-5 w-5 text-primary flex-shrink-0" />
            <h3 className="font-semibold text-base truncate">
              {outfit.reasoning || (badgeLabel ?? t('yourOutfit'))}
            </h3>
          </div>
          {badgeLabel && (
            <Badge variant="secondary" className="text-xs px-2 py-0.5 flex-shrink-0">
              {badgeLabel}
            </Badge>
          )}
        </div>
        {outfit.highlights && outfit.highlights.length > 0 && (
          <ul className="mt-2.5 space-y-1">
            {outfit.highlights.map((highlight, index) => (
              <li key={index} className="flex items-start gap-2 text-xs sm:text-sm text-muted-foreground">
                <span className="text-primary mt-0.5">•</span>
                <span>{highlight}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <CardContent className="p-4 flex-1 flex flex-col justify-between space-y-4">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          {outfit.items.map((item) => {
            const isBase = !!baseItemId && item.id === baseItemId;
            return (
              <Link
                key={item.id}
                href={`/dashboard/wardrobe?item=${item.id}`}
                className={cn(
                  'group relative rounded-xl border overflow-hidden bg-muted/30 hover:shadow-md transition-all',
                  isBase && 'border-primary/60 ring-2 ring-primary/20'
                )}
              >
                <div className="aspect-square relative">
                  {isBase && (
                    <Badge className="absolute top-2 left-2 z-10 bg-primary/95 text-primary-foreground text-[10px] px-2 py-0.5 shadow-sm">
                      {t('baseItem.basePiece')}
                    </Badge>
                  )}
                  {item.thumbnail_url ? (
                    <Image
                      src={item.thumbnail_url}
                      alt={item.name || item.type}
                      fill
                      className="object-cover group-hover:scale-105 transition-transform"
                      sizes="(max-width: 640px) 50vw, 33vw"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center bg-muted">
                      <Shirt className="h-8 w-8 text-muted-foreground/50" />
                    </div>
                  )}
                </div>
                <div className="p-2">
                  <p className="text-xs sm:text-sm font-medium truncate">
                    {item.name || item.type}
                  </p>
                  {item.layer_type && (
                    <Badge variant="secondary" className="text-[10px] capitalize mt-0.5">
                      {item.layer_type}
                    </Badge>
                  )}
                </div>
              </Link>
            );
          })}
        </div>

        {outfit.style_notes && (
          <div className="p-2.5 bg-muted/60 rounded-lg border text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">{t('tip')}</span> {outfit.style_notes}
          </div>
        )}

        {showActions && (
          <div className="pt-2 flex gap-2 justify-end border-t mt-auto">
            {onReject && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onReject}
                className="h-8 px-2.5 text-muted-foreground hover:text-destructive"
                aria-label={t('dismissOutfit')}
              >
                <ThumbsDown className="h-4 w-4" />
              </Button>
            )}
            {onAccept && (
              <Button size="sm" onClick={onAccept} className="gap-1.5 text-xs h-8">
                <ThumbsUp className="h-3.5 w-3.5" />
                {t('options.chooseThis')}
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function OutfitResultsView({
  outfits,
  occasion,
  temperatureUnit,
  baseItemId,
  activeOptionIndex,
  onSelectOption,
  isCompareAll,
  onToggleCompareAll,
  onAccept,
  onReject,
  onTryAnother,
  onNewRequest,
  t,
}: {
  outfits: Outfit[];
  occasion: string;
  temperatureUnit: TempUnit;
  baseItemId?: string;
  activeOptionIndex: number;
  onSelectOption: (index: number) => void;
  isCompareAll: boolean;
  onToggleCompareAll: () => void;
  onAccept: (outfit?: Outfit) => void;
  onReject: (outfit?: Outfit) => void;
  onTryAnother: () => void;
  onNewRequest: () => void;
  t: Translator;
}) {
  const currentOutfit = outfits[activeOptionIndex] || outfits[0];

  return (
    <div className="space-y-6">
      {/* Header with occasion and start over */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="capitalize text-sm px-3 py-1">
            {occasion}
          </Badge>
          {currentOutfit?.scheduled_for && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <CalendarDays className="h-3 w-3" />
              {new Date(currentOutfit.scheduled_for + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
            </span>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={onNewRequest}>
          {t('startOver')}
        </Button>
      </div>

      {/* Weather info */}
      {currentOutfit?.weather && (
        <div className="flex items-center gap-4 text-sm text-muted-foreground p-3 rounded-lg bg-muted/50">
          <div className="flex items-center gap-1.5">
            <Thermometer className="h-4 w-4" />
            <span>{formatTemp(currentOutfit.weather.temperature, temperatureUnit)}</span>
            <span className="text-xs opacity-70">{t('weather.feelsLikeInline', { temp: displayValue(currentOutfit.weather.feels_like, temperatureUnit) })}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Droplets className="h-4 w-4" />
            <span>{t('weather.rainChance', { chance: currentOutfit.weather.precipitation_chance })}</span>
          </div>
          <Badge variant="outline" className="capitalize">
            {currentOutfit.weather.condition}
          </Badge>
        </div>
      )}

      {/* Options Switcher Bar (when multiple outfits exist) */}
      {outfits.length > 1 && (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-1.5 bg-muted/60 rounded-xl border">
          <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none py-0.5">
            {outfits.map((opt, idx) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => onSelectOption(idx)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all flex items-center gap-1.5 flex-shrink-0',
                  !isCompareAll && activeOptionIndex === idx
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground hover:bg-background/50'
                )}
              >
                <Sparkles className={cn("h-3.5 w-3.5", !isCompareAll && activeOptionIndex === idx ? "text-primary" : "opacity-40")} />
                <span>{t('options.optionNumber', { number: idx + 1 })}</span>
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1 pt-1.5 sm:pt-0 border-t sm:border-t-0 justify-end">
            <Button
              variant={isCompareAll ? 'default' : 'ghost'}
              size="sm"
              className="h-7 text-xs gap-1.5"
              onClick={onToggleCompareAll}
            >
              <Layers className="h-3.5 w-3.5" />
              <span>{isCompareAll ? t('options.singleView') : t('options.allOptions')}</span>
            </Button>
          </div>
        </div>
      )}

      {/* View: All Outfits Side-by-Side Grid */}
      {isCompareAll ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {outfits.map((opt, idx) => (
              <OutfitCard
                key={opt.id}
                outfit={opt}
                baseItemId={baseItemId}
                temperatureUnit={temperatureUnit}
                t={t}
                badgeLabel={t('options.optionNumber', { number: idx + 1 })}
                onAccept={() => onAccept(opt)}
                onReject={() => onReject(opt)}
                showActions={true}
              />
            ))}
          </div>
          <div className="flex gap-3 justify-center pt-2">
            <Button variant="outline" size="lg" onClick={onTryAnother} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              {t('options.generateNew')}
            </Button>
          </div>
        </div>
      ) : (
        /* View: Single Active Outfit Focus */
        <div className="space-y-6">
          <OutfitCard
            outfit={currentOutfit}
            baseItemId={baseItemId}
            temperatureUnit={temperatureUnit}
            t={t}
            badgeLabel={outfits.length > 1 ? t('options.optionNumber', { number: activeOptionIndex + 1 }) : undefined}
            onAccept={() => onAccept(currentOutfit)}
            onReject={() => onReject(currentOutfit)}
            showActions={false}
          />

          {/* Action buttons */}
          <div className="flex gap-3 justify-center">
            <Button variant="outline" size="lg" onClick={onTryAnother} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              {outfits.length > 1 ? t('options.generateNew') : t('tryAnother')}
            </Button>
            <Button size="lg" onClick={() => onAccept(currentOutfit)} className="gap-2">
              <ThumbsUp className="h-4 w-4" />
              {t('loveIt')}
            </Button>
            <Button variant="ghost" size="lg" onClick={() => onReject(currentOutfit)} className="px-3" aria-label={t('dismissOutfit')}>
              <ThumbsDown className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function SuggestContent() {
  const t = useTranslations('suggest');
  const searchParams = useSearchParams();
  const preselectedItemId = searchParams.get('item');
  const { data: preselectedItem } = useItem(preselectedItemId || '');
  const { data: session } = useSession();
  const { data: weather, isLoading: weatherLoading } = useWeather();
  const { data: prefs } = usePreferences();
  const temperatureUnit: TempUnit = prefs?.temperature_unit === 'fahrenheit' ? 'fahrenheit' : 'celsius';
  const [selectedOccasion, setSelectedOccasion] = useState<string | null>(null);
  const [occasionInitialized, setOccasionInitialized] = useState(false);
  const [weatherOverride, setWeatherOverride] = useState<WeatherOverride | null>(null);
  const [selectedItem, setSelectedItem] = useState<Item | null>(null);
  const [isItemPickerOpen, setIsItemPickerOpen] = useState(false);
  const [filterType, setFilterType] = useState<string | undefined>(undefined);
  const [isGenerating, setIsGenerating] = useState(false);
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [activeOptionIndex, setActiveOptionIndex] = useState<number>(0);
  const [isCompareAll, setIsCompareAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (preselectedItem && !selectedItem) {
      setSelectedItem(preselectedItem);
    }
  }, [preselectedItem, selectedItem]);

  useEffect(() => {
    if (prefs?.default_occasion && !occasionInitialized && !selectedOccasion) {
      setSelectedOccasion(prefs.default_occasion);
      setOccasionInitialized(true);
    }
  }, [prefs, occasionInitialized, selectedOccasion]);

  const handleGenerate = async () => {
    if (!selectedOccasion) return;

    if (session?.accessToken) {
      setAccessToken(session.accessToken as string);
    }

    setIsGenerating(true);
    setError(null);

    try {
      const request: SuggestRequest = {
        occasion: selectedOccasion,
        include_items: selectedItem ? [selectedItem.id] : [],
      };

      if (weatherOverride) {
        request.weather_override = {
          temperature: weatherOverride.temperature,
          feels_like: weatherOverride.temperature,
          humidity: 50,
          precipitation_chance: weatherOverride.condition === 'rainy' ? 80 : weatherOverride.condition === 'cloudy' ? 30 : 10,
          condition: weatherOverride.condition,
        };
      }

      const result = await api.post<Outfit[]>('/outfits/suggest-options', request);
      setOutfits(result);
      setActiveOptionIndex(0);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(t('error'));
      }
      console.error('Suggestion error:', err);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleAccept = async (targetOutfit?: Outfit) => {
    const outfitToAccept = targetOutfit || outfits[activeOptionIndex];
    if (!outfitToAccept) return;

    if (session?.accessToken) {
      setAccessToken(session.accessToken as string);
    }

    try {
      await api.post(`/outfits/${outfitToAccept.id}/accept`);
      setOutfits([]);
      setSelectedOccasion(null);
    } catch (err) {
      console.error('Accept error:', err);
    }
  };

  const handleTryAnother = () => {
    setOutfits([]);
    handleGenerate();
  };

  const handleReject = async (targetOutfit?: Outfit) => {
    const outfitToReject = targetOutfit || outfits[activeOptionIndex];
    if (!outfitToReject) return;

    if (session?.accessToken) {
      setAccessToken(session.accessToken as string);
    }

    try {
      await api.post(`/outfits/${outfitToReject.id}/reject`);
    } catch (err) {
      console.error('Reject error:', err);
    }

    const remaining = outfits.filter((o) => o.id !== outfitToReject.id);
    if (remaining.length > 0) {
      setOutfits(remaining);
      setActiveOptionIndex((prev) => Math.min(prev, remaining.length - 1));
    } else {
      setOutfits([]);
      handleGenerate();
    }
  };

  const handleNewRequest = () => {
    setOutfits([]);
    setActiveOptionIndex(0);
    setIsCompareAll(false);
    setSelectedOccasion(null);
    setError(null);
  };

  return (
    <div
      className={cn(
        "mx-auto space-y-6 transition-all duration-300",
        isCompareAll && outfits.length > 0 ? "max-w-5xl" : "max-w-2xl"
      )}
    >
      {/* Page header with greeting */}
      <div className="text-center space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">{t(getGreetingKey())}</h1>
        <p className="text-muted-foreground">
          {t('subtitle')}
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {outfits.length === 0 ? (
        <div className="space-y-6">
          {/* Weather context */}
          <WeatherCard weather={weather} isLoading={weatherLoading} temperatureUnit={temperatureUnit} t={t} />

          {/* Main selection card */}
          <Card>
            <CardContent className="p-6 space-y-6">
              {/* Occasion selection */}
              <div className="space-y-3">
                <h2 className="font-semibold">{t('occasionPrompt')}</h2>
                <OccasionChips
                  selected={selectedOccasion}
                  onSelect={setSelectedOccasion}
                />
              </div>

              {/* Base item selection */}
              <div className="space-y-3 pt-1 border-t">
                <div className="space-y-0.5">
                  <h2 className="font-semibold text-sm sm:text-base flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-primary" />
                    {t('baseItem.title')}
                  </h2>
                  <p className="text-xs text-muted-foreground">
                    {t('baseItem.subtitle')}
                  </p>
                </div>

                {!selectedItem ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full h-16 border-dashed border-2 flex items-center justify-center gap-3 hover:border-primary/60 hover:bg-primary/5 transition-all text-muted-foreground hover:text-foreground"
                    onClick={() => setIsItemPickerOpen(true)}
                  >
                    <div className="p-2 rounded-full bg-muted">
                      <Plus className="h-4 w-4" />
                    </div>
                    <div className="text-left">
                      <span className="text-sm font-medium block text-foreground">
                        {t('baseItem.chooseItem')}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {t('baseItem.chooseItemHint')}
                      </span>
                    </div>
                  </Button>
                ) : (
                  <div className="flex items-center justify-between p-3 rounded-xl border bg-card/80 shadow-sm gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="relative w-14 h-14 rounded-lg overflow-hidden border bg-muted flex-shrink-0">
                        {selectedItem.thumbnail_url || selectedItem.image_url ? (
                          <Image
                            src={(selectedItem.thumbnail_url || selectedItem.image_url)!}
                            alt={selectedItem.name || selectedItem.type}
                            fill
                            className="object-cover"
                            sizes="56px"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center bg-muted">
                            <Shirt className="h-6 w-6 text-muted-foreground" />
                          </div>
                        )}
                      </div>
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-2">
                          <Badge variant="default" className="text-[10px] px-1.5 py-0">
                            {t('baseItem.mustInclude')}
                          </Badge>
                          <Badge variant="secondary" className="text-[10px] capitalize px-1.5 py-0">
                            {selectedItem.type}
                          </Badge>
                        </div>
                        <p className="text-sm font-medium truncate">
                          {selectedItem.name || selectedItem.type}
                        </p>
                        {selectedItem.primary_color && (
                          <p className="text-xs text-muted-foreground capitalize truncate">
                            {selectedItem.primary_color}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setIsItemPickerOpen(true)}
                        className="text-xs"
                      >
                        {t('baseItem.change')}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => setSelectedItem(null)}
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        title={t('baseItem.remove')}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              {/* Weather override (collapsible) */}
              <WeatherOverrideSection
                weather={weatherOverride}
                onChange={setWeatherOverride}
                temperatureUnit={temperatureUnit}
                t={t}
              />

              {/* Generate button */}
              <div className="pt-2">
                <Button
                  size="lg"
                  className="w-full gap-2"
                  onClick={handleGenerate}
                  disabled={!selectedOccasion || isGenerating}
                >
                  {isGenerating ? (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" />
                      {t('generating')}
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-5 w-5" />
                      {t('getSuggestion')}
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : (
        <OutfitResultsView
          outfits={outfits}
          activeOptionIndex={activeOptionIndex}
          onSelectOption={setActiveOptionIndex}
          isCompareAll={isCompareAll}
          onToggleCompareAll={() => setIsCompareAll(!isCompareAll)}
          occasion={selectedOccasion || 'casual'}
          temperatureUnit={temperatureUnit}
          baseItemId={selectedItem?.id}
          onAccept={handleAccept}
          onReject={handleReject}
          onTryAnother={handleTryAnother}
          onNewRequest={handleNewRequest}
          t={t}
        />
      )}

      {/* Item Picker Dialog */}
      <Dialog open={isItemPickerOpen} onOpenChange={setIsItemPickerOpen}>
        <DialogContent className="sm:max-w-xl max-h-[85vh] flex flex-col p-6">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              {t('baseItem.dialogTitle')}
            </DialogTitle>
            <DialogDescription>
              {t('baseItem.dialogDescription')}
            </DialogDescription>
          </DialogHeader>

          {/* Quick Category Filter Chips */}
          <div className="flex gap-1.5 overflow-x-auto py-1 scrollbar-none">
            {[
              { label: t('baseItem.all'), value: undefined },
              { label: 'Shirt', value: 'shirt' },
              { label: 'T-Shirt', value: 't-shirt' },
              { label: 'Pants', value: 'pants' },
              { label: 'Jeans', value: 'jeans' },
              { label: 'Shoes', value: 'shoes' },
              { label: 'Sneakers', value: 'sneakers' },
              { label: 'Jacket', value: 'jacket' },
              { label: 'Dress', value: 'dress' },
            ].map((cat) => (
              <Button
                key={cat.value ?? 'all'}
                type="button"
                variant={filterType === cat.value ? 'default' : 'outline'}
                size="sm"
                className="text-xs h-7 px-2.5 rounded-full flex-shrink-0"
                onClick={() => setFilterType(cat.value)}
              >
                {cat.label}
              </Button>
            ))}
          </div>

          <div className="flex-1 overflow-hidden min-h-0 pt-1">
            <ItemPicker
              key={filterType ?? 'all'}
              selectedIds={selectedItem ? new Set([selectedItem.id]) : new Set()}
              onToggle={(item) => {
                if (selectedItem?.id === item.id) {
                  setSelectedItem(null);
                } else {
                  setSelectedItem(item);
                  setIsItemPickerOpen(false);
                }
              }}
              filterType={filterType}
              hideNeedsWash={true}
              heightClass="h-[340px]"
            />
          </div>

          <div className="flex justify-between items-center pt-3 border-t mt-2">
            {selectedItem ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setSelectedItem(null)}
                className="text-xs text-muted-foreground hover:text-destructive"
              >
                {t('baseItem.clear')}
              </Button>
            ) : <div />}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsItemPickerOpen(false)}
            >
              Done
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function SuggestPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-2xl mx-auto space-y-6">
          <div className="space-y-2 text-center">
            <Skeleton className="h-8 w-48 mx-auto" />
            <Skeleton className="h-4 w-64 mx-auto" />
          </div>
          <Card>
            <CardContent className="p-6 space-y-4">
              <Skeleton className="h-24 w-full rounded-lg" />
              <Skeleton className="h-10 w-full" />
            </CardContent>
          </Card>
        </div>
      }
    >
      <SuggestContent />
    </Suspense>
  );
}
