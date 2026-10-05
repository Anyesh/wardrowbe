import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable, applySessionToken } from '@/lib/hooks/use-session-token';
import { queryKeys } from '@/lib/hooks/query-keys';
import { SLOW_STALE_TIME } from '@/lib/hooks/query-timing';
import type { InsightParams } from '@/lib/insights';

// Types for learning API responses
export interface LearnedColorScore {
  color: string;
  score: number;
  interpretation: string; // "strongly liked", "liked", "neutral", "disliked", "strongly disliked"
}

export interface LearnedStyleScore {
  style: string;
  score: number;
}

export interface OccasionPattern {
  occasion: string;
  preferred_colors: string[];
  success_rate: number;
}

export interface WeatherPreference {
  weather_type: string; // cold, cool, mild, hot
  preferred_layers: number;
  success_rate: number;
}

export interface LearningProfile {
  has_learning_data: boolean;
  feedback_count: number;
  outfits_rated: number;
  overall_acceptance_rate: number | null;
  average_rating: number | null;
  average_comfort_rating: number | null;
  average_style_rating: number | null;
  color_preferences: LearnedColorScore[];
  style_preferences: LearnedStyleScore[];
  occasion_patterns: OccasionPattern[];
  weather_preferences: WeatherPreference[];
  last_computed_at: string | null;
}

export interface ItemInfo {
  id: string;
  type: string;
  name: string | null;
  primary_color: string | null;
  thumbnail_path: string | null;
  thumbnail_url: string | null;
}

export interface ItemPair {
  item1: ItemInfo;
  item2: ItemInfo;
  compatibility_score: number;
  times_paired: number;
  times_accepted: number;
}

export interface StyleInsight {
  id: string;
  category: string;
  insight_type: string;
  title: string;
  description: string;
  confidence: number;
  created_at: string;
  // title and description are English; message_key renders them in the user's language.
  message_key?: string | null;
  message_params?: InsightParams;
}

export interface PreferenceSuggestions {
  updated: boolean;
  suggestions?: {
    suggested_favorite_colors?: string[];
    suggested_avoid_colors?: string[];
  };
  confidence?: number | null;
  reason?: string;
}

export interface LearningInsightsData {
  profile: LearningProfile;
  best_pairs: ItemPair[];
  insights: StyleInsight[];
  preference_suggestions: PreferenceSuggestions;
}

export interface ItemPairSuggestion {
  item: ItemInfo;
  compatibility_score: number;
}

/**
 * Hook to fetch learning insights for the current user.
 * Returns the user's learning profile, best item pairs, and style insights.
 */
export function useLearning() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.learning.all,
    queryFn: () => api.get<LearningInsightsData>('/learning'),
    enabled: status !== 'loading',
    staleTime: SLOW_STALE_TIME,
  });
}

/**
 * Hook to recompute the learning profile.
 * Triggers a full recomputation of learned preferences from feedback history.
 */
export function useRecomputeLearning() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async () => {
      applySessionToken(session);
      return api.post<LearningProfile>('/learning/recompute');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.learning.all });
    },
  });
}

/**
 * Hook to generate new style insights.
 * Creates human-readable insights about the user's style patterns.
 */
export function useGenerateInsights() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async () => {
      applySessionToken(session);
      return api.post<StyleInsight[]>('/learning/generate-insights');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.learning.all });
    },
  });
}

/**
 * Hook to acknowledge/dismiss an insight.
 */
export function useAcknowledgeInsight() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (insightId: string) => {
      applySessionToken(session);
      return api.post<{ acknowledged: boolean }>(`/learning/insights/${insightId}/acknowledge`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.learning.all });
    },
  });
}

/**
 * Hook to get items that pair well with a specific item.
 */
export function useItemPairSuggestions(itemId: string, limit = 5) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.learning.itemPairs(itemId, limit),
    queryFn: () => api.get<ItemPairSuggestion[]>(`/learning/item-pairs/${itemId}`, {
      params: { limit: String(limit) },
    }),
    enabled: status !== 'loading' && !!itemId,
    staleTime: SLOW_STALE_TIME,
  });
}
