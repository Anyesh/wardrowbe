'use client';

import {
  Brain,
  Lightbulb,
  TrendingUp,
  Activity,
  Sparkles,
  RefreshCw,
  ThumbsUp,
  ThumbsDown,
  Shirt,
  X,
  Heart,
  Cloud,
  Calendar,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import {
  useLearning,
  useRecomputeLearning,
  useGenerateInsights,
  useAcknowledgeInsight,
  type ItemPair,
  type StyleInsight,
  type LearnedColorScore,
} from '@/lib/hooks/use-learning';
import { useI18n } from '@/lib/i18n';
import Image from 'next/image';
import Link from 'next/link';
import { useState } from 'react';

function StatCard({
  title,
  value,
  description,
  icon: Icon,
  trend,
}: {
  title: string;
  value: string | number;
  description: React.ReactNode;
  icon: React.ComponentType<{ className?: string }>;
  trend?: 'up' | 'down' | 'neutral';
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        <p className="text-xs text-muted-foreground flex items-center gap-1">
          {trend === 'up' && <TrendingUp className="h-3 w-3 text-green-500" />}
          {trend === 'down' && <TrendingUp className="h-3 w-3 text-red-500 rotate-180" />}
          {description}
        </p>
      </CardContent>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16 mb-1" />
              <Skeleton className="h-3 w-32" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-6 w-full" />
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-6 w-full" />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

const colorMap: Record<string, string> = {
  black: 'bg-gray-900',
  white: 'bg-gray-100 border',
  gray: 'bg-gray-500',
  grey: 'bg-gray-500',
  navy: 'bg-blue-900',
  blue: 'bg-blue-500',
  red: 'bg-red-500',
  green: 'bg-green-500',
  yellow: 'bg-yellow-400',
  orange: 'bg-orange-500',
  purple: 'bg-purple-500',
  pink: 'bg-pink-500',
  brown: 'bg-amber-700',
  beige: 'bg-amber-200',
  cream: 'bg-amber-100',
  khaki: 'bg-yellow-700',
  olive: 'bg-lime-700',
  teal: 'bg-teal-500',
  burgundy: 'bg-red-900',
  maroon: 'bg-red-800',
};

function ColorPreferenceBar({ colorScore }: { colorScore: LearnedColorScore }) {
  const bgColor = colorMap[colorScore.color.toLowerCase()] || 'bg-muted';
  const score = colorScore.score;
  const percentage = Math.abs(score) * 100;
  const isPositive = score >= 0;

  return (
    <div className="flex items-center gap-3">
      <div className={`w-4 h-4 rounded ${bgColor}`} />
      <div className="flex-1">
        <div className="flex justify-between text-sm mb-1">
          <span className="capitalize">{colorScore.color}</span>
          <span className="text-muted-foreground flex items-center gap-1">
            {isPositive ? (
              <ThumbsUp className="h-3 w-3 text-green-500" />
            ) : (
              <ThumbsDown className="h-3 w-3 text-red-500" />
            )}
            {colorScore.interpretation}
          </span>
        </div>
        <div className="h-2 bg-muted rounded overflow-hidden">
          <div
            className={`h-full rounded ${isPositive ? 'bg-green-500' : 'bg-red-500'}`}
            style={{ width: `${Math.min(percentage, 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function ItemPairCard({ pair }: { pair: ItemPair }) {
  const { t } = useI18n();
  const successRate = pair.times_paired > 0
    ? Math.round((pair.times_accepted / pair.times_paired) * 100)
    : 0;

  return (
    <div className="flex items-center gap-4 p-3 rounded-lg bg-muted/50">
      <div className="flex items-center gap-2 flex-1">
        {/* Item 1 */}
        <Link
          href={`/dashboard/wardrobe/${pair.item1.id}`}
          className="w-12 h-12 rounded bg-background overflow-hidden relative flex-shrink-0 hover:ring-2 ring-primary transition-all"
        >
          {pair.item1.thumbnail_url ? (
            <Image
              src={pair.item1.thumbnail_url}
              alt={pair.item1.name || pair.item1.type}
              fill
              className="object-cover"
              sizes="48px"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <Shirt className="h-6 w-6 text-muted-foreground" />
            </div>
          )}
        </Link>

        {/* Plus sign */}
        <div className="text-muted-foreground text-lg">+</div>

        {/* Item 2 */}
        <Link
          href={`/dashboard/wardrobe/${pair.item2.id}`}
          className="w-12 h-12 rounded bg-background overflow-hidden relative flex-shrink-0 hover:ring-2 ring-primary transition-all"
        >
          {pair.item2.thumbnail_url ? (
            <Image
              src={pair.item2.thumbnail_url}
              alt={pair.item2.name || pair.item2.type}
              fill
              className="object-cover"
              sizes="48px"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <Shirt className="h-6 w-6 text-muted-foreground" />
            </div>
          )}
        </Link>
      </div>

      <div className="text-right">
        <div className="flex items-center gap-1 justify-end">
          <Heart className="h-4 w-4 text-red-500" />
          <span className="font-medium">{successRate}%</span>
        </div>
        <div className="text-xs text-muted-foreground">
          {pair.times_paired}{t('learning.paired')}
        </div>
      </div>
    </div>
  );
}

function InsightCard({
  insight,
  onAcknowledge
}: {
  insight: StyleInsight;
  onAcknowledge: (id: string) => void;
}) {
  const { t } = useI18n();

  const categoryIcons: Record<string, React.ComponentType<{ className?: string }>> = {
    color: Sparkles,
    style: Heart,
    overall: Activity,
    weather: Cloud,
    occasion: Calendar,
  };

  const typeColors: Record<string, string> = {
    positive: 'border-green-500/30 bg-green-500/10',
    negative: 'border-red-500/30 bg-red-500/10',
    suggestion: 'border-blue-500/30 bg-blue-500/10',
    pattern: 'border-purple-500/30 bg-purple-500/10',
  };

  const Icon = categoryIcons[insight.category] || Lightbulb;
  const borderColor = typeColors[insight.insight_type] || 'border-muted';

  return (
    <div className={`p-4 rounded-lg border-2 ${borderColor} relative`}>
      <button
        onClick={() => onAcknowledge(insight.id)}
        className="absolute top-2 right-2 p-1 rounded hover:bg-muted transition-colors"
        title={t('learning.dismiss')}
      >
        <X className="h-4 w-4 text-muted-foreground" />
      </button>
      <div className="flex items-start gap-3 pr-6">
        <Icon className="h-5 w-5 text-muted-foreground flex-shrink-0 mt-0.5" />
        <div>
          <h4 className="font-medium">{insight.title}</h4>
          <p className="text-sm text-muted-foreground mt-1">{insight.description}</p>
          <div className="flex items-center gap-2 mt-2">
            <Badge variant="outline" className="text-xs">
              {insight.category}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {Math.round(insight.confidence * 100)}{t('learning.confidence')}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function NoLearningData({ onRecompute, isRefreshing }: { onRecompute: () => void; isRefreshing: boolean }) {
  const { t } = useI18n();
  return (
    <Card className="col-span-full">
      <CardContent className="flex flex-col items-center justify-center py-12 text-center">
        <Brain className="h-12 w-12 text-muted-foreground mb-4" />
        <h3 className="text-lg font-semibold mb-2">{t('learning.empty')}</h3>
        <p className="text-muted-foreground max-w-md mb-4">
          {t('learning.getStarted')}
        </p>
        <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
          <Link href="/dashboard/suggest" className="w-full sm:w-auto">
            <Button className="w-full sm:w-auto">
              <Sparkles className="h-4 w-4 mr-2" />
              {t('learning.getSuggestions')}
            </Button>
          </Link>
          <Button
            variant="outline"
            onClick={onRecompute}
            disabled={isRefreshing}
            className="w-full sm:w-auto"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            {isRefreshing ? t('learning.computing') : t('learning.computeNow')}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-4">
          {t('learning.alreadyFed')}
        </p>
      </CardContent>
    </Card>
  );
}

export default function LearningPage() {
  const { t } = useI18n();
  const { data, isLoading, isError } = useLearning();
  const recompute = useRecomputeLearning();
  const generateInsights = useGenerateInsights();
  const acknowledgeInsight = useAcknowledgeInsight();
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRecompute = async () => {
    setIsRefreshing(true);
    try {
      await recompute.mutateAsync();
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleGenerateInsights = async () => {
    await generateInsights.mutateAsync();
  };

  const handleAcknowledgeInsight = (insightId: string) => {
    acknowledgeInsight.mutate(insightId);
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{t('learning.title')}</h1>
            <p className="text-muted-foreground">{t('learning.loadingSubtitle')}</p>
          </div>
        </div>
        <LoadingSkeleton />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-center py-8 text-red-500">
        {t('learning.loadFailed')}
      </div>
    );
  }

  const { profile, best_pairs, insights, preference_suggestions } = data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t('learning.title')}</h1>
          <p className="text-muted-foreground">
            {profile.has_learning_data
              ? t('learning.subtitle')
              : t('learning.subtitleEmpty')}
          </p>
        </div>
        {profile.has_learning_data && (
          <Button
            variant="outline"
            onClick={handleRecompute}
            disabled={isRefreshing}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            {t('learning.recompute')}
          </Button>
        )}
      </div>

      {!profile.has_learning_data ? (
        <NoLearningData onRecompute={handleRecompute} isRefreshing={isRefreshing} />
      ) : (
        <>
          {/* Stats Cards */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <StatCard
              title={t('learning.feedbackGiven')}
              value={profile.feedback_count}
              description={<>{profile.outfits_rated} {t('learning.outfitsRated')}</>}
              icon={Activity}
            />
            <StatCard
              title={t('learning.acceptanceRate')}
              value={profile.overall_acceptance_rate
                ? `${Math.round(profile.overall_acceptance_rate * 100)}%`
                : '-'}
              description={profile.overall_acceptance_rate
                ? t('learning.ofAccepted')
                : t('learning.notEnoughData')}
              icon={TrendingUp}
              trend={profile.overall_acceptance_rate && profile.overall_acceptance_rate > 0.5 ? 'up' : undefined}
            />
            <StatCard
              title={t('learning.avgRating')}
              value={profile.average_rating ? profile.average_rating.toFixed(1) : '-'}
              description={profile.average_rating ? t('learning.outOf5') : t('learning.rateMore')}
              icon={Sparkles}
            />
            <StatCard
              title={t('learning.styleRating')}
              value={profile.average_style_rating ? profile.average_style_rating.toFixed(1) : '-'}
              description={profile.average_style_rating ? t('learning.styleSatisfaction') : t('learning.rateStyles')}
              icon={Heart}
            />
          </div>

          {/* Active Insights */}
          {insights.length > 0 && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Lightbulb className="h-5 w-5" />
                    {t('learning.styleInsights')}
                  </CardTitle>
                  <CardDescription>{t('learning.whatLearned')}</CardDescription>
                </div>
                <Button variant="ghost" size="sm" onClick={handleGenerateInsights}>
                  <RefreshCw className="h-4 w-4 mr-1" />
                  {t('learning.newInsights')}
                </Button>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 md:grid-cols-2">
                  {insights.map((insight) => (
                    <InsightCard
                      key={insight.id}
                      insight={insight}
                      onAcknowledge={handleAcknowledgeInsight}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            {/* Color Preferences */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="h-5 w-5" />
                  {t('learning.colorPrefs')}
                </CardTitle>
                <CardDescription>{t('learning.colorPrefsDesc')}</CardDescription>
              </CardHeader>
              <CardContent>
                {profile.color_preferences.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    {t('learning.colorNotEnough')}
                  </p>
                ) : (
                  <div className="space-y-3">
                    {profile.color_preferences.slice(0, 8).map((colorScore) => (
                      <ColorPreferenceBar key={colorScore.color} colorScore={colorScore} />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Style Preferences */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Heart className="h-5 w-5" />
                  {t('learning.stylePrefs')}
                </CardTitle>
                <CardDescription>{t('learning.stylePrefsDesc')}</CardDescription>
              </CardHeader>
              <CardContent>
                {profile.style_preferences.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    {t('learning.styleNotEnough')}
                  </p>
                ) : (
                  <div className="space-y-3">
                    {profile.style_preferences.map((styleScore) => {
                      const isPositive = styleScore.score >= 0;
                      const percentage = Math.abs(styleScore.score) * 100;
                      return (
                        <div key={styleScore.style} className="flex items-center justify-between">
                          <span className="capitalize">{styleScore.style}</span>
                          <div className="flex items-center gap-2">
                            <Progress
                              value={percentage}
                              className={`w-24 h-2 ${isPositive ? '' : '[&>div]:bg-red-500'}`}
                            />
                            <span className="text-sm text-muted-foreground w-12 text-right">
                              {isPositive ? '+' : ''}{(styleScore.score * 100).toFixed(0)}%
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Best Item Pairs */}
          {best_pairs.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Heart className="h-5 w-5 text-red-500" />
                  {t('learning.bestCombos')}
                </CardTitle>
                <CardDescription>{t('learning.bestCombosDesc')}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                  {best_pairs.map((pair, index) => (
                    <ItemPairCard key={index} pair={pair} />
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Occasion Patterns */}
          {profile.occasion_patterns.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5" />
                  {t('learning.occasionPatterns')}
                </CardTitle>
                <CardDescription>{t('learning.occasionPatternsDesc')}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {profile.occasion_patterns.map((pattern) => (
                    <div key={pattern.occasion} className="p-4 rounded-lg bg-muted/50">
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="font-medium capitalize">{pattern.occasion}</h4>
                        <Badge variant="outline">
                          {Math.round(pattern.success_rate * 100)}{t('learning.success')}
                        </Badge>
                      </div>
                      {pattern.preferred_colors.length > 0 && (
                        <div className="flex items-center gap-2 mt-2">
                          <span className="text-xs text-muted-foreground">{t('learning.preferredColors')}</span>
                          <div className="flex gap-1">
                            {pattern.preferred_colors.map((color) => (
                              <div
                                key={color}
                                className={`w-4 h-4 rounded ${colorMap[color.toLowerCase()] || 'bg-muted'}`}
                                title={color}
                              />
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Weather Preferences */}
          {profile.weather_preferences.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Cloud className="h-5 w-5" />
                  {t('learning.weatherPrefs')}
                </CardTitle>
                <CardDescription>{t('learning.weatherPrefsDesc')}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                  {profile.weather_preferences.map((pref) => (
                    <div key={pref.weather_type} className="p-4 rounded-lg bg-muted/50 text-center">
                      <div className="text-2xl mb-1">
                        {pref.weather_type === 'cold' && '❄️'}
                        {pref.weather_type === 'cool' && '🍂'}
                        {pref.weather_type === 'mild' && '🌤️'}
                        {pref.weather_type === 'hot' && '☀️'}
                      </div>
                      <h4 className="font-medium capitalize">{pref.weather_type}</h4>
                      <p className="text-sm text-muted-foreground mt-1">
                        ~{pref.preferred_layers.toFixed(1)} {t('learning.layers')}
                      </p>
                      <Badge variant="outline" className="mt-2">
                        {Math.round(pref.success_rate * 100)}{t('learning.success')}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Preference Suggestions */}
          {preference_suggestions.updated && preference_suggestions.suggestions && (
            <Card className="border-primary/50">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Lightbulb className="h-5 w-5 text-primary" />
                  {t('learning.suggestedUpdates')}
                </CardTitle>
                <CardDescription>
                  {t('learning.suggestedUpdatesDesc')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {preference_suggestions.suggestions.suggested_favorite_colors && (
                    <div className="flex items-center gap-3">
                      <span className="text-sm">{t('learning.addFavColors')}</span>
                      <div className="flex gap-2">
                        {preference_suggestions.suggestions.suggested_favorite_colors.map((color) => (
                          <Badge key={color} variant="secondary" className="capitalize">
                            <div className={`w-3 h-3 rounded mr-1 ${colorMap[color.toLowerCase()] || 'bg-muted'}`} />
                            {color}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {preference_suggestions.suggestions.suggested_avoid_colors && (
                    <div className="flex items-center gap-3">
                      <span className="text-sm">{t('learning.addAvoidColors')}</span>
                      <div className="flex gap-2">
                        {preference_suggestions.suggestions.suggested_avoid_colors.map((color) => (
                          <Badge key={color} variant="destructive" className="capitalize">
                            <div className={`w-3 h-3 rounded mr-1 ${colorMap[color.toLowerCase()] || 'bg-muted'}`} />
                            {color}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <div className="mt-4">
                  <Link href="/dashboard/settings">
                    <Button variant="outline" size="sm">
                      {t('learning.updatePrefs')}
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Last Updated */}
          {profile.last_computed_at && (
            <p className="text-xs text-muted-foreground text-center">
              {t('learning.lastUpdated')} {new Date(profile.last_computed_at).toLocaleString()}
            </p>
          )}
        </>
      )}
    </div>
  );
}