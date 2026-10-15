'use client';

import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import { useTranslations } from 'next-intl';
import { Loader2, MessageCircleHeart, Send, Trash2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ApiError } from '@/lib/api';
import { useStylist, type StylistTurn } from '@/lib/hooks/use-stylist';
import { useTypeLabel } from '@/lib/hooks/use-translated-constants';
import type { Item } from '@/lib/types';

const STORAGE_KEY = 'wardrowbe.stylistChat';
const ITEM_TOKEN = /\[\[item:([0-9a-f-]{36})\]\]/g;

interface ChatMessage extends StylistTurn {
  items?: Item[];
}

function MessageBody({ message }: { message: ChatMessage }) {
  const typeLabel = useTypeLabel();
  const byId = new Map((message.items ?? []).map((item) => [item.id, item]));
  const parts = message.content.split(ITEM_TOKEN);
  return (
    <div className="whitespace-pre-line leading-relaxed">
      {parts.map((part, index) => {
        if (index % 2 === 0) return <span key={index}>{part}</span>;
        const item = byId.get(part);
        if (!item) return null;
        return (
          <span
            key={index}
            className="mx-0.5 inline-flex items-center gap-1 rounded-md border bg-background px-1 py-0.5 align-middle text-xs"
          >
            {item.thumbnail_url && (
              <span className="relative inline-block h-6 w-6 overflow-hidden rounded">
                <Image
                  src={item.thumbnail_url}
                  alt={item.name || typeLabel(item.type)}
                  fill
                  className="object-cover"
                  sizes="24px"
                />
              </span>
            )}
            {item.name || typeLabel(item.type)}
          </span>
        );
      })}
    </div>
  );
}

export default function StylistPage() {
  const t = useTranslations('stylist');
  const stylist = useStylist();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const saved = window.sessionStorage.getItem(STORAGE_KEY);
      if (saved) setMessages(JSON.parse(saved));
    } catch {
      // A fresh chat when the saved one cannot be read.
    }
  }, []);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {
      // Private mode: the chat lasts until the page closes.
    }
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = (text: string) => {
    const content = text.trim();
    if (!content || stylist.isPending) return;
    const next: ChatMessage[] = [...messages, { role: 'user', content }];
    setMessages(next);
    setDraft('');
    stylist.mutate(
      next.slice(-20).map(({ role, content: body }) => ({ role, content: body })),
      {
        onSuccess: (reply) =>
          setMessages((current) => [
            ...current,
            { role: 'assistant', content: reply.reply, items: reply.items },
          ]),
      }
    );
  };

  const errorText =
    stylist.error instanceof ApiError && stylist.error.status === 503
      ? t('aiOff')
      : stylist.error
        ? t('aiError')
        : null;
  const examples = [t('examples.today'), t('examples.match'), t('examples.event')];

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <MessageCircleHeart className="h-6 w-6" />
            {t('title')}
          </h1>
          <p className="text-muted-foreground">{t('subtitle')}</p>
        </div>
        {messages.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setMessages([])} disabled={stylist.isPending}>
            <Trash2 className="mr-1 h-4 w-4" />
            {t('clear')}
          </Button>
        )}
      </div>

      <Card>
        <CardContent className="space-y-4 pt-6">
          {messages.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">{t('intro')}</p>
              <div className="flex flex-wrap gap-2">
                {examples.map((example) => (
                  <Button key={example} variant="outline" size="sm" onClick={() => send(example)}>
                    {example}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {messages.map((message, index) => (
            <div key={index} className={message.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
                  message.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'
                }`}
              >
                <MessageBody message={message} />
              </div>
            </div>
          ))}
          {stylist.isPending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('thinking')}
            </div>
          )}
          {errorText && <p className="text-sm text-destructive">{errorText}</p>}
          <div ref={bottom} />
        </CardContent>
      </Card>

      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send(draft);
            }
          }}
          placeholder={t('placeholder')}
          aria-label={t('placeholder')}
          rows={2}
          maxLength={2000}
        />
        <Button type="submit" disabled={!draft.trim() || stylist.isPending} aria-label={t('send')}>
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}
