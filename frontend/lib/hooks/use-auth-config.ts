'use client';

import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

export interface AuthConfig {
  oidc: {
    enabled: boolean;
    issuer_url: string | null;
    client_id: string | null;
  };
  dev_mode: boolean;
  forward_auth: boolean;
  mobile_notice: string | null;
}

export function useAuthConfig() {
  return useQuery({
    queryKey: ['auth-config'],
    queryFn: () => api.get<AuthConfig>('/auth/config'),
    staleTime: Infinity,
    retry: false,
  });
}
