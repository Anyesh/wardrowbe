'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable, applySessionToken } from '@/lib/hooks/use-session-token';
import { queryKeys } from '@/lib/hooks/query-keys';

export type NotificationChannel = 'ntfy' | 'mattermost' | 'email' | 'expo_push';

// expo_push is registered by the mobile app through /notifications/push-token, never from the form.
export type ManualNotificationChannel = Exclude<NotificationChannel, 'expo_push'>;

export interface NotificationSettings {
  id: string;
  user_id: string;
  channel: NotificationChannel;
  enabled: boolean;
  priority: number;
  config: Record<string, string>;
  created_at: string;
  updated_at: string;
  // Set when a stored config fails this version's validation; the dispatcher skips past it.
  config_error: string | null;
}

export interface Schedule {
  id: string;
  user_id: string;
  day_of_week: number;
  notification_time: string;
  occasion: string;
  enabled: boolean;
  notify_day_before: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationHistory {
  id: string;
  user_id: string;
  outfit_id?: string;
  channel: string;
  status: string;
  attempts: number;
  sent_at?: string;
  delivered_at?: string;
  error_message?: string;
  created_at: string;
}

export function useNotificationSettings() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.notificationSettings,
    queryFn: () => api.get<NotificationSettings[]>('/notifications/settings'),
    enabled: status !== 'loading',
  });
}

export function useCreateNotificationSetting() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (data: {
      channel: ManualNotificationChannel;
      enabled: boolean;
      priority: number;
      config: Record<string, string>;
    }) => {
      applySessionToken(session);
      return api.post<NotificationSettings>('/notifications/settings', data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notificationSettings });
    },
  });
}

export function useUpdateNotificationSetting() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      data: Partial<{ enabled: boolean; priority: number; config: Record<string, string> }>;
    }) => {
      applySessionToken(session);
      return api.patch<NotificationSettings>(`/notifications/settings/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notificationSettings });
    },
  });
}

export function useDeleteNotificationSetting() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (id: string) => {
      applySessionToken(session);
      return api.delete(`/notifications/settings/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notificationSettings });
    },
  });
}

export function useTestNotificationSetting() {
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (id: string) => {
      applySessionToken(session);
      return api.post<{ success: boolean; message: string }>(
        `/notifications/settings/${id}/test`
      );
    },
  });
}

export function useSchedules() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.schedules,
    queryFn: () => api.get<Schedule[]>('/notifications/schedules'),
    enabled: status !== 'loading',
  });
}

export function useCreateSchedule() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (data: {
      day_of_week: number;
      notification_time: string;
      occasion: string;
      enabled: boolean;
      notify_day_before?: boolean;
    }) => {
      applySessionToken(session);
      return api.post<Schedule>('/notifications/schedules', data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules });
    },
  });
}

export function useUpdateSchedule() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      data: Partial<{ notification_time: string; occasion: string; enabled: boolean; notify_day_before: boolean }>;
    }) => {
      applySessionToken(session);
      return api.patch<Schedule>(`/notifications/schedules/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules });
    },
  });
}

export function useDeleteSchedule() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (id: string) => {
      applySessionToken(session);
      return api.delete(`/notifications/schedules/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules });
    },
  });
}

export function useNotificationHistory(limit = 20) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.notificationHistory(limit),
    queryFn: () => api.get<NotificationHistory[]>(`/notifications/history?limit=${limit}`),
    enabled: status !== 'loading',
  });
}
