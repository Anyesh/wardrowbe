'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, setAccessToken } from '@/lib/api';
import { Family, FamilyCreateResponse, JoinFamilyResponse, FamilyMember } from '@/lib/types';

// Helper to set token if available (for NextAuth mode)
function useSetTokenIfAvailable() {
  const { data: session } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }
}

export function useFamily() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['family'],
    queryFn: () => api.get<Family>('/families/me'),
    // Fetch when session is loaded (works with both NextAuth and forward auth)
    enabled: status !== 'loading',
    retry: false, // Don't retry on 404 (user not in family)
  });
}

export function useCreateFamily() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (name: string) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<FamilyCreateResponse>('/families', { name });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family'] });
    },
  });
}

export function useUpdateFamily() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (name: string) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.patch<Family>('/families/me', { name });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family'] });
    },
  });
}

export function useJoinFamily() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (inviteCode: string) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<JoinFamilyResponse>('/families/join', { invite_code: inviteCode });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family'] });
    },
  });
}

export function useJoinFamilyByToken() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (token: string) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<JoinFamilyResponse>('/families/join-by-token', { token });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family'] });
    },
  });
}

export function useLeaveFamily() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async () => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<{ message: string }>('/families/me/leave');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family'] });
    },
  });
}

export function useRegenerateInviteCode() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async () => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<{ invite_code: string }>('/families/me/regenerate-code');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family'] });
    },
  });
}

export function useInviteMember() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ email, role }: { email: string; role?: string }) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<{ id: string; email: string; expires_at: string }>(
        '/families/me/invite',
        { email, role: role || 'member' }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family'] });
    },
  });
}

export function useCancelInvite() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (inviteId: string) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.delete(`/families/me/invites/${inviteId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family'] });
    },
  });
}

export function useUpdateMemberRole() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ memberId, role }: { memberId: string; role: string }) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.patch<FamilyMember>(`/families/me/members/${memberId}`, { role });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family'] });
    },
  });
}

export function useRemoveMember() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (memberId: string) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.delete(`/families/me/members/${memberId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family'] });
    },
  });
}
