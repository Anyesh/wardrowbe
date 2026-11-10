'use client';

import { useMutation } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { API_BASE_PATH, ApiError, getAccessToken } from '@/lib/api';
import type { Item } from '@/lib/types';

export interface SelfieResult {
  matches: Item[];
  considered: number;
}

export function useSelfieRecognition() {
  const { data: session } = useSession();
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('image', file);
      const token = session?.accessToken || getAccessToken();
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const response = await fetch(`${API_BASE_PATH}/selfie`, {
        method: 'POST',
        body: formData,
        credentials: 'include',
        headers,
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new ApiError(
          typeof data.detail === 'string' ? data.detail : 'Request failed',
          response.status,
          data
        );
      }
      return response.json() as Promise<SelfieResult>;
    },
  });
}
