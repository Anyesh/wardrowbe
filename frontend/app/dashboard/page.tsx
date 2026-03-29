'use client';

import { useMemo } from 'react';
import { useSession } from 'next-auth/react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Shirt,
  Sparkles,
  Plus,
  TrendingUp,
  Cloud,
  Droplets,
  ThumbsUp,
  ThumbsDown,
  Clock,
  Bell,
  BellOff,
  Calendar,
  CheckCircle2,
  XCircle,
  Lightbulb,
  ChevronRight,
  HeartHandshake,
  Users,
} from 'lucide-react';
import Link from 'next/link';
import Image from 'next/image';
import { useAnalytics } from '@/lib/hooks/use-analytics';
import { useWeather } from '@/lib/hooks/use-weather';
import { usePreferences } from '@/lib/hooks/use-preferences';
import { displayValue, tempSymbol, TempUnit } from '@/lib/temperature';
import { usePendingOutfits, useAcceptOutfit, useRejectOutfit } from '@/lib/hooks/use-outfits';
import { useSchedules, useNotificationSettings } from '@/lib/hooks/use-notifications';
import { useFamily } from '@/lib/hooks/use-family';
import { toast } from 'sonner';

function WeatherCard() {
  const { data: weather, isLoading, isError } = useWeather();
  const { data: prefs } = usePreferences();
  const unit: TempUnit = prefs?.temperature_unit === 'fahrenheit' ? 'fahrenheit' : 'celsius';

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Cloud className="h-4 w-4" />
            Today&apos;s Weather
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-12 w-24 mb-2" />
          <Skeleton className="h-4 w-32" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !weather) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Cloud className="h-4 w-4" />
            Today&apos;s Weather
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-3">
            Location not set
          </p>
          <Button size="sm" variant="outline" asChild>
            <Link href="/dashboard/settings">Set Location</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Cloud className="h-4 w-4" />
          Today&apos;s Weather
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline gap-2 mb-1">
          <span className="text-3xl font-bold">{displayValue(weather.temperature, unit)}{tempSymbol(unit)}</span>
          <span className="text-muted-foreground text-sm">
            feels {displayValue(weather.feels_like, unit)}°
          </span>
        </div>
        <p className="text-sm text-muted-foreground capitalize mb-1">
          {weather.condition}
        </p>
        {weather.precipitation_chance > 0 && (
          <p className="text-xs text-muted-foreground flex items-center gap-1">
            <Droplets className="h-3 w-3" />
            {weather.precipitation_chance}% chance of rain
          </p>
        )}
        <Button size="sm" className="w-full mt-3" asChild>
          <Link href="/dashboard/suggest">
            <Sparkles className="h-4 w-4 mr-1" />
            Get Outfit Suggestion
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function PendingOutfitsCard() {
  const { data, isLoading } = usePendingOutfits(2);
  const acceptOutfit = useAcceptOutfit();
  const rejectOutfit = useRejectOutfit();

  const handleAccept = async (id: string) => {
    try {
      await acceptOutfit.mutateAsync(id);
      toast.success('Outfit accepted');
    } catch {
      toast.error('Failed to accept outfit');
    }
  };

  const handleReject = async (id: string) => {
    try {
      await rejectOutfit.mutateAsync(id);
      toast.success('Outfit rejected');
    } catch {
      toast.error('Failed to reject outfit');
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Clock className="h-4 w-4" />
            Pending Outfits
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full mb-2" />
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  const pendingOutfits = data?.outfits || [];

  if (pendingOutfits.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-500" />
            All Caught Up
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No outfits waiting for your response
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Clock className="h-4 w-4 text-orange-500" />
            Pending Outfits
            <Badge variant="secondary" className="ml-1">{data?.total || pendingOutfits.length}</Badge>
          </CardTitle>
          {(data?.total ?? 0) > 2 && (
            <Link href="/dashboard/history" className="text-xs text-muted-foreground hover:text-foreground">
              View all
            </Link>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {pendingOutfits.map((outfit) => (
          <div key={outfit.id} className="flex items-center gap-3">
            <div className="flex -space-x-2">
              {outfit.items.slice(0, 3).map((item) => (
                <div
                  key={item.id}
                  className="w-10 h-10 rounded-full bg-muted overflow-hidden relative border-2 border-background"
                >
                  {item.thumbnail_url ? (
                    <Image
                      src={item.thumbnail_url}
                      alt={item.name || item.type}
                      fill
                      className="object-cover"
                      sizes="40px"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <Shirt className="h-4 w-4 text-muted-foreground" />
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium capitalize truncate">{outfit.occasion}</p>
              <p className="text-xs text-muted-foreground">
                {new Date(outfit.scheduled_for).toLocaleDateString('en-US', {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                })}
              </p>
            </div>
            <div className="flex gap-1">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-red-500 hover:text-red-600 hover:bg-red-50"
                onClick={() => handleReject(outfit.id)}
                disabled={rejectOutfit.isPending}
              >
                <ThumbsDown className="h-4 w-4" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-green-500 hover:text-green-600 hover:bg-green-50"
                onClick={() => handleAccept(outfit.id)}
                disabled={acceptOutfit.isPending}
              >
                <ThumbsUp className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function NextScheduledCard() {
  const { data: schedules, isLoading } = useSchedules();

  const nextSchedule = useMemo(() => {
    if (!schedules || schedules.length === 0) return null;

    const enabledSchedules = schedules.filter((s) => s.enabled);
    if (enabledSchedules.length === 0) return null;

    const now = new Date();
    const currentDay = now.getDay();
    const currentTime = now.getHours() * 60 + now.getMinutes();

    // Find the next scheduled notification
    let closest: { schedule: typeof enabledSchedules[0]; daysUntil: number; minutesUntil: number } | null = null;

    for (const schedule of enabledSchedules) {
      const [hours, minutes] = schedule.notification_time.split(':').map(Number);
      const scheduleMinutes = hours * 60 + minutes;

      let daysUntil = schedule.day_of_week - currentDay;
      if (daysUntil < 0 || (daysUntil === 0 && scheduleMinutes <= currentTime)) {
        daysUntil += 7;
      }

      const minutesUntil = daysUntil === 0 ? scheduleMinutes - currentTime : scheduleMinutes;

      if (!closest || daysUntil < closest.daysUntil || (daysUntil === closest.daysUntil && minutesUntil < closest.minutesUntil)) {
        closest = { schedule, daysUntil, minutesUntil };
      }
    }

    return closest;
  }, [schedules]);

  const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            Next Scheduled
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-6 w-32 mb-1" />
          <Skeleton className="h-4 w-24" />
        </CardContent>
      </Card>
    );
  }

  if (!nextSchedule) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            Next Scheduled
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-2">No schedules set up</p>
          <Button size="sm" variant="outline" asChild>
            <Link href="/dashboard/notifications">Set Up Schedule</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const { schedule, daysUntil } = nextSchedule;
  const timeStr = schedule.notification_time.slice(0, 5);
  const dayStr = daysUntil === 0 ? 'Today' : daysUntil === 1 ? 'Tomorrow' : dayNames[schedule.day_of_week];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Calendar className="h-4 w-4" />
          Next Scheduled
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-semibold">
          {dayStr} at {timeStr}
        </p>
        <p className="text-sm text-muted-foreground capitalize">
          {schedule.occasion} outfit
        </p>
        {daysUntil === 0 && (
          <Badge variant="secondary" className="mt-2">Coming up</Badge>
        )}
      </CardContent>
    </Card>
  );
}

function NotificationStatusCard() {
  const { data: settings, isLoading } = useNotificationSettings();

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Bell className="h-4 w-4" />
            Notifications
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-4 w-full mb-2" />
          <Skeleton className="h-4 w-24" />
        </CardContent>
      </Card>
    );
  }

  const channels = settings || [];
  const enabledChannels = channels.filter((c) => c.enabled);

  if (channels.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <BellOff className="h-4 w-4 text-muted-foreground" />
            Notifications
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-2">No channels configured</p>
          <Button size="sm" variant="outline" asChild>
            <Link href="/dashboard/notifications">Add Channel</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Bell className="h-4 w-4" />
            Notifications
          </CardTitle>
          <Link href="/dashboard/notifications" className="text-xs text-muted-foreground hover:text-foreground">
            Configure
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {channels.map((channel) => (
            <Badge
              key={channel.id}
              variant={channel.enabled ? 'default' : 'outline'}
              className={channel.enabled ? '' : 'text-muted-foreground'}
            >
              {channel.enabled ? (
                <CheckCircle2 className="h-3 w-3 mr-1" />
              ) : (
                <XCircle className="h-3 w-3 mr-1" />
              )}
              {channel.channel}
            </Badge>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          {enabledChannels.length} of {channels.length} active
        </p>
      </CardContent>
    </Card>
  );
}

function WeeklySummaryCard() {
  const { data: analytics, isLoading } = useAnalytics();

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            This Week
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-8 w-16 mb-1" />
          <Skeleton className="h-4 w-32" />
        </CardContent>
      </Card>
    );
  }

  if (!analytics) {
    return null;
  }

  const { wardrobe } = analytics;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <TrendingUp className="h-4 w-4" />
          This Week
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-2xl font-bold">{wardrobe.outfits_this_week}</p>
            <p className="text-xs text-muted-foreground">outfits</p>
          </div>
          <div>
            <p className="text-2xl font-bold">
              {wardrobe.acceptance_rate ? `${wardrobe.acceptance_rate}%` : '-'}
            </p>
            <p className="text-xs text-muted-foreground">accepted</p>
          </div>
        </div>
        {wardrobe.average_rating && (
          <p className="text-xs text-muted-foreground mt-2">
            Avg rating: {wardrobe.average_rating}/5
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function InsightsCard() {
  const { data: analytics, isLoading } = useAnalytics();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lightbulb className="h-5 w-5" />
            Insights
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        </CardContent>
      </Card>
    );
  }

  const insights = analytics?.insights || [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Lightbulb className="h-5 w-5" />
            Insights
          </CardTitle>
          {insights.length > 3 && (
            <Link href="/dashboard/analytics" className="text-sm text-muted-foreground hover:text-foreground flex items-center">
              View all <ChevronRight className="h-4 w-4" />
            </Link>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {insights.length > 0 ? (
          <ul className="space-y-2 text-sm">
            {insights.slice(0, 3).map((insight, i) => (
              <li key={i} className="flex items-start gap-2">
                <div className="h-1.5 w-1.5 rounded-full bg-primary mt-2 flex-shrink-0" />
                <span className="text-muted-foreground">{insight}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">
            Add more items and generate outfits to see personalized insights!
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function FamilyFeedCard() {
  const { data: family, isLoading } = useFamily();

  if (isLoading) return null;

  // Don't show if user has no family
  if (!family) return null;

  const memberCount = family.members.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HeartHandshake className="h-5 w-5" />
          Family Outfits
        </CardTitle>
        <CardDescription>
          See what your family is wearing and rate their outfits
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Users className="h-4 w-4" />
          <span>{memberCount} member{memberCount !== 1 ? 's' : ''} in {family.name}</span>
        </div>
        <Button asChild className="w-full">
          <Link href="/dashboard/family/feed">
            Browse Family Outfits
            <ChevronRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function QuickActionsCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick Actions</CardTitle>
        <CardDescription>Common tasks to get you started</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button asChild className="w-full justify-start">
          <Link href="/dashboard/wardrobe">
            <Plus className="mr-2 h-4 w-4" />
            Add New Item
          </Link>
        </Button>
        <Button asChild variant="outline" className="w-full justify-start">
          <Link href="/dashboard/suggest">
            <Sparkles className="mr-2 h-4 w-4" />
            Get Outfit Suggestion
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { data: session } = useSession();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Welcome back, {session?.user?.name?.split(' ')[0] || 'User'}
        </h1>
        <p className="text-muted-foreground">
          Here&apos;s what&apos;s happening with your wardrobe
        </p>
      </div>

      {/* Top row - Weather + Pending + Next Scheduled */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <WeatherCard />
        <PendingOutfitsCard />
        <NextScheduledCard />
      </div>

      {/* Second row - Weekly Summary + Notification Status */}
      <div className="grid gap-4 md:grid-cols-2">
        <WeeklySummaryCard />
        <NotificationStatusCard />
      </div>

      {/* Third row - Quick Actions + Insights */}
      <div className="grid gap-4 md:grid-cols-2">
        <QuickActionsCard />
        <InsightsCard />
      </div>

      {/* Family feed card */}
      <FamilyFeedCard />
    </div>
  );
}
