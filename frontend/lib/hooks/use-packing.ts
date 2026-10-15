'use client';

import { useMutation } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { applySessionToken } from '@/lib/hooks/use-session-token';
import type { Item } from '@/lib/types';

export interface PackingRequest {
  destination: string;
  start_date: string;
  end_date: string;
  occasion: string;
  laundry: boolean;
}

export interface PackingDay {
  date: string;
  temp_min: number;
  temp_max: number;
  precipitation_chance: number;
  condition: string;
}

export interface PackingGroup {
  role: string;
  needed: number;
  items: Item[];
}

export interface PackingPlan {
  destination: string;
  latitude: number;
  longitude: number;
  start_date: string;
  end_date: string;
  days: number;
  season: string;
  estimated: boolean;
  temp_min: number;
  temp_max: number;
  rain_days: number;
  forecast: PackingDay[];
  groups: PackingGroup[];
  missing_roles: string[];
}

export function usePackingPlan() {
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (request: PackingRequest) => {
      applySessionToken(session);
      return api.post<PackingPlan>('/packing', request);
    },
  });
}
