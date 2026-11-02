'use client';

import { useMutation } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { applySessionToken } from '@/lib/hooks/use-session-token';
import type { Item } from '@/lib/types';

export interface StylistTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface StylistReply {
  reply: string;
  items: Item[];
}

export function useStylist() {
  const { data: session } = useSession();
  return useMutation({
    mutationFn: async (messages: StylistTurn[]) => {
      applySessionToken(session);
      return api.post<StylistReply>('/stylist', { messages });
    },
  });
}
