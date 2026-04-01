'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useSession } from 'next-auth/react';
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
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { api, ApiError, setAccessToken } from '@/lib/api';
import { OCCASIONS, Outfit, SuggestRequest } from '@/lib/types';
import { useWeather, Weather } from '@/lib/hooks/use-weather';
import { usePreferences } from '@/lib/hooks/use-preferences';
import { cn } from '@/lib/utils';
import { TempUnit, formatTemp, displayValue, toF, toCelsius } from '@/lib/temperature';

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

// Get time-based greeting
function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

// Get weather-based outfit hint
function getWeatherHint(weather: Weather): string {
  const temp = weather.temperature;
  const condition = weather.condition.toLowerCase();

  if (weather.precipitation_chance > 50) return 'Bring an umbrella or rain jacket';
  if (temp < 10) return 'Layer up - it\'s quite cold';
  if (temp < 18) return 'A light jacket would be perfect';
  if (temp > 28) return 'Keep it light and breathable';
  if (condition.includes('wind')) return 'Consider something windproof';
  return 'Great weather for any style';
}

interface WeatherOverride {
  temperature: number;
  condition: 'sunny' | 'cloudy' | 'rainy';
}

function WeatherCard({ weather, isLoading, temperatureUnit }: { weather?: Weather; isLoading: boolean; temperatureUnit: TempUnit }) {
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
              <p className="font-medium">Location not set</p>
              <p className="text-sm text-muted-foreground">
                Set your location in settings for weather-aware suggestions
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
              <span>Feels {displayValue(weather.feels_like, temperatureUnit)}°</span>
            </div>
            <div className="flex items-center gap-1.5 justify-end">
              <Droplets className="h-3.5 w-3.5" />
              <span>{weather.precipitation_chance}% rain</span>
            </div>
            <div className="flex items-center gap-1.5 justify-end">
              <Wind className="h-3.5 w-3.5" />
              <span>{Math.round(weather.wind_speed)} km/h</span>
            </div>
          </div>
        </div>
        <div className="mt-4 pt-4 border-t">
          <p className="text-sm text-muted-foreground">
            {getWeatherHint(weather)}
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
  return (
    <div className="flex flex-wrap gap-2">
      {OCCASIONS.map((occasion) => {
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
}: {
  weather: WeatherOverride | null;
  onChange: (weather: WeatherOverride | null) => void;
  temperatureUnit: TempUnit;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const conditions = [
    { value: 'sunny', icon: <Sun className="h-4 w-4" />, label: 'Sunny' },
    { value: 'cloudy', icon: <Cloud className="h-4 w-4" />, label: 'Cloudy' },
    { value: 'rainy', icon: <CloudRain className="h-4 w-4" />, label: 'Rainy' },
  ] as const;

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ChevronDown className={cn('h-4 w-4 transition-transform', isOpen && 'rotate-180')} />
          <span>{weather ? 'Weather override active' : 'Override weather'}</span>
          {weather && (
            <Badge variant="secondary" className="text-xs">
              {weather.condition} {formatTemp(weather.temperature, temperatureUnit)}
            </Badge>
          )}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-4">
        <div className="space-y-4 p-4 rounded-lg bg-muted/50">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Condition</span>
            {weather && (
              <Button variant="ghost" size="sm" onClick={() => onChange(null)}>
                Reset
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
                <span className="text-sm">{c.label}</span>
              </button>
            ))}
          </div>
          {weather && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">Temperature</span>
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

function OutfitResult({
  outfit,
  occasion,
  temperatureUnit,
  onAccept,
  onReject,
  onTryAnother,
  onNewRequest,
}: {
  outfit: Outfit;
  occasion: string;
  temperatureUnit: TempUnit;
  onAccept: () => void;
  onReject: () => void;
  onTryAnother: () => void;
  onNewRequest: () => void;
}) {
  return (
    <div className="space-y-6">
      {/* Header with occasion and new request */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="capitalize text-sm px-3 py-1">
            {occasion}
          </Badge>
          {outfit.scheduled_for && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <CalendarDays className="h-3 w-3" />
              {new Date(outfit.scheduled_for + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
            </span>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={onNewRequest}>
          Start over
        </Button>
      </div>

      {/* Weather info */}
      {outfit.weather && (
        <div className="flex items-center gap-4 text-sm text-muted-foreground p-3 rounded-lg bg-muted/50">
          <div className="flex items-center gap-1.5">
            <Thermometer className="h-4 w-4" />
            <span>{formatTemp(outfit.weather.temperature, temperatureUnit)}</span>
            <span className="text-xs opacity-70">(feels {displayValue(outfit.weather.feels_like, temperatureUnit)}°)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Droplets className="h-4 w-4" />
            <span>{outfit.weather.precipitation_chance}% rain</span>
          </div>
          <Badge variant="outline" className="capitalize">
            {outfit.weather.condition}
          </Badge>
        </div>
      )}

      {/* Outfit Card */}
      <Card className="overflow-hidden">
        <div className="bg-gradient-to-r from-primary/10 to-primary/5 p-4 border-b">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            <h3 className="font-semibold">Your Outfit</h3>
          </div>
          {outfit.reasoning && (
            <p className="mt-2 text-base font-medium text-foreground">{outfit.reasoning}</p>
          )}
          {outfit.highlights && outfit.highlights.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {outfit.highlights.map((highlight, index) => (
                <li key={index} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <span className="text-primary mt-0.5">•</span>
                  <span>{highlight}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <CardContent className="p-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {outfit.items.map((item) => (
              <Link
                key={item.id}
                href={`/dashboard/wardrobe?item=${item.id}`}
                className="group relative rounded-xl border overflow-hidden bg-muted/30 hover:shadow-md transition-shadow"
              >
                <div className="aspect-square relative">
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
                      <Shirt className="h-10 w-10 text-muted-foreground/50" />
                    </div>
                  )}
                </div>
                <div className="p-2.5">
                  <p className="text-sm font-medium truncate">
                    {item.name || item.type}
                  </p>
                  {item.layer_type && (
                    <Badge variant="secondary" className="text-xs capitalize mt-1">
                      {item.layer_type}
                    </Badge>
                  )}
                </div>
              </Link>
            ))}
          </div>

          {outfit.style_notes && (
            <div className="mt-4 p-3 bg-muted rounded-lg border">
              <p className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Tip:</span> {outfit.style_notes}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Action buttons */}
      <div className="flex gap-3 justify-center">
        <Button variant="outline" size="lg" onClick={onTryAnother} className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Try Another
        </Button>
        <Button size="lg" onClick={onAccept} className="gap-2">
          <ThumbsUp className="h-4 w-4" />
          Love it
        </Button>
        <Button variant="ghost" size="lg" onClick={onReject} className="px-3">
          <ThumbsDown className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export default function SuggestPage() {
  const { data: session } = useSession();
  const { data: weather, isLoading: weatherLoading } = useWeather();
  const { data: prefs } = usePreferences();
  const temperatureUnit: TempUnit = prefs?.temperature_unit === 'fahrenheit' ? 'fahrenheit' : 'celsius';
  const [selectedOccasion, setSelectedOccasion] = useState<string | null>(null);
  const [occasionInitialized, setOccasionInitialized] = useState(false);
  const [weatherOverride, setWeatherOverride] = useState<WeatherOverride | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [outfit, setOutfit] = useState<Outfit | null>(null);
  const [error, setError] = useState<string | null>(null);

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

      const result = await api.post<Outfit>('/outfits/suggest', request);
      setOutfit(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to generate outfit suggestion. Please try again.');
      }
      console.error('Suggestion error:', err);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleAccept = async () => {
    if (!outfit) return;

    if (session?.accessToken) {
      setAccessToken(session.accessToken as string);
    }

    try {
      await api.post(`/outfits/${outfit.id}/accept`);
      setOutfit(null);
      setSelectedOccasion(null);
    } catch (err) {
      console.error('Accept error:', err);
    }
  };

  const handleTryAnother = () => {
    setOutfit(null);
    handleGenerate();
  };

  const handleReject = async () => {
    if (!outfit) return;

    if (session?.accessToken) {
      setAccessToken(session.accessToken as string);
    }

    try {
      await api.post(`/outfits/${outfit.id}/reject`);
    } catch (err) {
      console.error('Reject error:', err);
    }

    setOutfit(null);
    handleGenerate();
  };

  const handleNewRequest = () => {
    setOutfit(null);
    setSelectedOccasion(null);
    setError(null);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Page header with greeting */}
      <div className="text-center space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">{getGreeting()}</h1>
        <p className="text-muted-foreground">
          Let&apos;s find the perfect outfit for your day
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!outfit ? (
        <div className="space-y-6">
          {/* Weather context */}
          <WeatherCard weather={weather} isLoading={weatherLoading} temperatureUnit={temperatureUnit} />

          {/* Main selection card */}
          <Card>
            <CardContent className="p-6 space-y-6">
              {/* Occasion selection */}
              <div className="space-y-3">
                <h2 className="font-semibold">What&apos;s the occasion?</h2>
                <OccasionChips
                  selected={selectedOccasion}
                  onSelect={setSelectedOccasion}
                />
              </div>

              {/* Weather override (collapsible) */}
              <WeatherOverrideSection
                weather={weatherOverride}
                onChange={setWeatherOverride}
                temperatureUnit={temperatureUnit}
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
                      Creating your look...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-5 w-5" />
                      Get Suggestion
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : (
        <OutfitResult
          outfit={outfit}
          occasion={selectedOccasion || 'casual'}
          temperatureUnit={temperatureUnit}
          onAccept={handleAccept}
          onReject={handleReject}
          onTryAnother={handleTryAnother}
          onNewRequest={handleNewRequest}
        />
      )}
    </div>
  );
}
