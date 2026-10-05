import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import { queryKeys } from '@/lib/hooks/query-keys';

export interface ColorDistribution {
  color: string;
  count: number;
  percentage: number;
}

export interface TypeDistribution {
  type: string;
  count: number;
  percentage: number;
}

export interface WearStats {
  id: string;
  name: string | null;
  type: string;
  primary_color: string | null;
  thumbnail_path: string | null;
  thumbnail_url: string | null;
  wear_count: number;
  last_worn_at: string | null;
}

export interface AcceptanceRateTrend {
  period: string;
  total: number;
  accepted: number;
  rejected: number;
  rate: number;
}

export interface WardrobeStats {
  total_items: number;
  items_by_status: Record<string, number>;
  total_outfits: number;
  outfits_this_week: number;
  outfits_this_month: number;
  acceptance_rate: number | null;
  average_rating: number | null;
  total_wears: number;
}

export interface AnalyticsData {
  wardrobe: WardrobeStats;
  color_distribution: ColorDistribution[];
  type_distribution: TypeDistribution[];
  most_worn: WearStats[];
  least_worn: WearStats[];
  never_worn: WearStats[];
  acceptance_trend: AcceptanceRateTrend[];
  insights: string[];
}

export function useAnalytics(days = 30) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.analytics.summary(days),
    queryFn: () => api.get<AnalyticsData>('/analytics', {
      params: { days: String(days) },
    }),
    enabled: status !== 'loading',
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
