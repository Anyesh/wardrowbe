'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Camera, CheckCircle2, Circle, Loader2, Sparkles } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ACCEPTED_IMAGE_INPUT } from '@/lib/image-types';
import { ApiError } from '@/lib/api';
import { useLogWear } from '@/lib/hooks/use-items';
import { useSelfieRecognition } from '@/lib/hooks/use-selfie';
import { useTypeLabel } from '@/lib/hooks/use-translated-constants';

export default function SelfiePage() {
  const t = useTranslations('selfie');
  const typeLabel = useTypeLabel();
  const recognise = useSelfieRecognition();
  const logWear = useLogWear();
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  const logged = useRef<Set<string>>(new Set());
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const choose = (next: File | null) => {
    setFile(next);
    setSelected(new Set());
    setDone(false);
    logged.current = new Set();
    recognise.reset();
    if (next) {
      recognise.mutate(next, {
        onSuccess: (result) => setSelected(new Set(result.matches.map((item) => item.id))),
      });
    }
  };

  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const confirm = async () => {
    setSaving(true);
    try {
      // Each wear is its own request: after a failure, a retry skips the ones already logged
      // instead of counting them twice.
      for (const id of Array.from(selected)) {
        if (logged.current.has(id)) continue;
        await logWear.mutateAsync({ id });
        logged.current.add(id);
      }
      setDone(true);
      toast.success(t('saved', { count: selected.size }));
    } catch {
      toast.error(t('saveError'));
    } finally {
      setSaving(false);
    }
  };

  const errorText =
    recognise.error instanceof ApiError && recognise.error.status === 503
      ? t('aiOff')
      : recognise.error
        ? t('aiError')
        : null;
  const matches = recognise.data?.matches ?? [];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <Camera className="h-6 w-6" />
          {t('title')}
        </h1>
        <p className="text-muted-foreground">{t('subtitle')}</p>
      </div>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground hover:bg-accent">
            {preview ? (
              // eslint-disable-next-line @next/next/no-img-element -- a local blob preview
              <img src={preview} alt={t('photoAlt')} className="max-h-80 rounded-md object-contain" />
            ) : (
              <>
                <Camera className="h-8 w-8" />
                <span className="font-medium text-foreground">{t('pick')}</span>
                <span>{t('pickHint')}</span>
              </>
            )}
            <input
              type="file"
              accept={ACCEPTED_IMAGE_INPUT}
              className="hidden"
              onChange={(e) => {
                choose(e.target.files?.[0] ?? null);
                e.target.value = '';
              }}
            />
          </label>

          {recognise.isPending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('working')}
            </div>
          )}
          {errorText && <p className="text-sm text-destructive">{errorText}</p>}
        </CardContent>
      </Card>

      {recognise.isSuccess && (
        <Card>
          <CardContent className="space-y-4 pt-6">
            <div className="flex items-center gap-2 font-medium">
              <Sparkles className="h-4 w-4" />
              {matches.length > 0 ? t('found', { count: matches.length }) : t('noneFound')}
            </div>
            {matches.length > 0 && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {matches.map((item) => {
                  const on = selected.has(item.id);
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => toggle(item.id)}
                      aria-pressed={on}
                      disabled={done}
                      className={`rounded-lg border p-2 text-left transition ${on ? 'border-primary' : 'opacity-50'}`}
                    >
                      <div className="relative mb-2 aspect-square overflow-hidden rounded-md bg-muted">
                        {item.thumbnail_url && (
                          <Image
                            src={item.thumbnail_url}
                            alt={item.name || typeLabel(item.type)}
                            fill
                            className="object-cover"
                            sizes="160px"
                          />
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        {on ? (
                          <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />
                        ) : (
                          <Circle className="h-4 w-4 shrink-0 text-muted-foreground" />
                        )}
                        <span className="truncate">{item.name || typeLabel(item.type)}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
            <p className="text-xs text-muted-foreground">{t('checkHint')}</p>
            <Button onClick={confirm} disabled={selected.size === 0 || saving || done}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {done ? t('savedButton') : t('confirm', { count: selected.size })}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
