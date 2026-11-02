'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  CheckCircle2,
  ExternalLink,
  ImagePlus,
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  ShoppingBag,
  Trash2,
  TrendingDown,
  Undo2,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ACCEPTED_IMAGE_INPUT } from '@/lib/image-types';
import { ApiError, getErrorMessage } from '@/lib/api';
import {
  useAddWishlistEntry,
  useCheckPrices,
  useDeleteWishlistEntry,
  useLinkPreview,
  useUpdateWishlistEntry,
  useUploadWishlistPhoto,
  useWishlist,
  useWishlistSuggestions,
  type WishlistEntry,
} from '@/lib/hooks/use-wishlist';
import { useClothingTypes, useRoleLabel, useTypeLabel } from '@/lib/hooks/use-translated-constants';

const NO_TYPE = 'none';
const PRIORITIES = [1, 2, 3] as const;

function money(locale: string, value: string | null): string | null {
  if (value == null || Number(value) <= 0) return null;
  return new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' }).format(Number(value));
}

function EntryCard({ entry }: { entry: WishlistEntry }) {
  const t = useTranslations('wishlist');
  const locale = useLocale();
  const typeLabel = useTypeLabel();
  const update = useUpdateWishlistEntry();
  const remove = useDeleteWishlistEntry();
  const upload = useUploadWishlistPhoto();
  const fileInput = useRef<HTMLInputElement>(null);
  const price = money(locale, entry.price);
  const dropped = entry.price_dropped_at && entry.current_price ? money(locale, entry.current_price) : null;
  const fail = (error: unknown) => toast.error(getErrorMessage(error, t('error')));

  return (
    <Card className={entry.bought ? 'opacity-60' : undefined}>
      <CardContent className="space-y-3 pt-6">
        <div className="relative aspect-square overflow-hidden rounded-md bg-muted">
          {entry.photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- shop pictures live on any domain
            <img
              src={entry.photo_url}
              alt={entry.name}
              className="h-full w-full object-cover"
              referrerPolicy="no-referrer"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <ShoppingBag className="h-10 w-10" />
            </div>
          )}
          <Badge className="absolute left-2 top-2" variant={entry.priority === 1 ? 'destructive' : 'secondary'}>
            {t(`priority.${entry.priority}`)}
          </Badge>
        </div>
        <div className="space-y-1">
          <div className="flex items-start justify-between gap-2">
            <span className="font-medium leading-tight">{entry.name}</span>
            {dropped ? (
              <span className="shrink-0 text-right text-sm">
                <span className="font-semibold text-green-600">{dropped}</span>{' '}
                <span className="text-xs text-muted-foreground line-through">{price}</span>
              </span>
            ) : (
              price && <span className="shrink-0 text-sm font-semibold">{price}</span>
            )}
          </div>
          {dropped && (
            <Badge className="gap-1 bg-green-600 hover:bg-green-600">
              <TrendingDown className="h-3 w-3" />
              {t('price.dropped')}
            </Badge>
          )}
          {entry.item_type && (
            <div className="text-xs text-muted-foreground">{typeLabel(entry.item_type)}</div>
          )}
          {entry.notes && <p className="whitespace-pre-line text-sm text-muted-foreground">{entry.notes}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {entry.link && (
            <Button asChild size="sm" variant="outline">
              <a href={entry.link} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="mr-1 h-3 w-3" />
                {t('actions.open')}
              </a>
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            disabled={update.isPending}
            onClick={() => update.mutate({ id: entry.id, bought: !entry.bought }, { onError: fail })}
          >
            {entry.bought ? <Undo2 className="mr-1 h-3 w-3" /> : <CheckCircle2 className="mr-1 h-3 w-3" />}
            {entry.bought ? t('actions.notBought') : t('actions.bought')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={upload.isPending}
            onClick={() => fileInput.current?.click()}
            aria-label={t('actions.photo')}
          >
            {upload.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <ImagePlus className="h-3 w-3" />}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={remove.isPending}
            onClick={() => remove.mutate(entry.id, { onError: fail })}
            aria-label={t('actions.delete')}
          >
            <Trash2 className="h-3 w-3" />
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED_IMAGE_INPUT}
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate({ id: entry.id, file }, { onError: fail });
              e.target.value = '';
            }}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function AddForm({ initialName }: { initialName: string }) {
  const t = useTranslations('wishlist');
  const locale = useLocale();
  const types = useClothingTypes();
  const add = useAddWishlistEntry();
  const upload = useUploadWishlistPhoto();
  const preview = useLinkPreview();
  const [link, setLink] = useState('');
  const [name, setName] = useState(initialName);
  const [imageUrl, setImageUrl] = useState('');
  const [price, setPrice] = useState('');
  const [itemType, setItemType] = useState(NO_TYPE);
  const [priority, setPriority] = useState('2');
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState<File | null>(null);

  const readLink = () =>
    preview.mutate(link.trim(), {
      onSuccess: (data) => {
        if (data.title && !name) setName(data.title);
        if (data.image_url) setImageUrl(data.image_url);
        if (data.price) setPrice(String(Number(data.price)));
        toast.success(t('form.linkRead', { site: data.site ?? '' }));
      },
      onError: (error) =>
        toast.error(error instanceof ApiError && error.status === 400 ? t('form.linkUnreadable') : t('error')),
    });

  const reset = () => {
    setLink('');
    setName('');
    setImageUrl('');
    setPrice('');
    setItemType(NO_TYPE);
    setPriority('2');
    setNotes('');
    setFile(null);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const entry = await add.mutateAsync({
        name: name.trim(),
        link: link.trim() || null,
        image_url: imageUrl.trim() || null,
        price: price.trim() ? price.trim().replace(',', '.') : null,
        item_type: itemType === NO_TYPE ? null : itemType,
        priority: Number(priority),
        notes: notes.trim() || null,
      });
      if (file) await upload.mutateAsync({ id: entry.id, file });
      toast.success(t('form.added', { name: entry.name }));
      reset();
    } catch (error) {
      toast.error(
        error instanceof ApiError && error.status === 422 ? t('form.invalid') : getErrorMessage(error, t('error'))
      );
    }
  };

  const localPreview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => {
    if (localPreview) URL.revokeObjectURL(localPreview);
  }, [localPreview]);
  const shownImage = localPreview ?? imageUrl;

  return (
    <form onSubmit={submit} className="grid gap-4 md:grid-cols-[160px_1fr]">
      <label className="relative flex aspect-square cursor-pointer items-center justify-center overflow-hidden rounded-md border border-dashed bg-muted text-muted-foreground">
        {shownImage ? (
          // eslint-disable-next-line @next/next/no-img-element -- local preview or a shop picture
          <img src={shownImage} alt={name || t('form.photo')} className="h-full w-full object-cover" referrerPolicy="no-referrer" />
        ) : (
          <span className="flex flex-col items-center gap-1 text-xs">
            <ImagePlus className="h-6 w-6" />
            {t('form.photo')}
          </span>
        )}
        <input
          type="file"
          accept={ACCEPTED_IMAGE_INPUT}
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>
      <div className="space-y-3">
        <div className="flex gap-2">
          <Input
            value={link}
            onChange={(e) => setLink(e.target.value)}
            placeholder={t('form.linkPlaceholder')}
            aria-label={t('form.link')}
            inputMode="url"
          />
          <Button type="button" variant="outline" disabled={!link.trim() || preview.isPending} onClick={readLink}>
            {preview.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
            <span className="ml-1 hidden sm:inline">{t('form.readLink')}</span>
          </Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
          <div className="space-y-1">
            <Label htmlFor="wish-name">{t('form.name')}</Label>
            <Input id="wish-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="wish-price">{t('form.price')}</Label>
            <Input
              id="wish-price"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              inputMode="decimal"
              placeholder={money(locale, '49.9') ?? ''}
            />
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Select value={itemType} onValueChange={setItemType}>
            <SelectTrigger aria-label={t('form.type')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_TYPE}>{t('form.anyType')}</SelectItem>
              {types.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={priority} onValueChange={setPriority}>
            <SelectTrigger aria-label={t('form.priority')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PRIORITIES.map((p) => (
                <SelectItem key={p} value={String(p)}>
                  {t(`priority.${p}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={t('form.notesPlaceholder')}
          aria-label={t('form.notes')}
          rows={2}
          maxLength={2000}
        />
        <Button type="submit" disabled={!name.trim() || add.isPending || upload.isPending}>
          {add.isPending || upload.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Plus className="mr-2 h-4 w-4" />
          )}
          {t('form.add')}
        </Button>
      </div>
    </form>
  );
}

export default function WishlistPage() {
  const t = useTranslations('wishlist');
  const locale = useLocale();
  const roleLabel = useRoleLabel();
  const { data, isLoading } = useWishlist();
  const { data: gaps } = useWishlistSuggestions();
  const checkPrices = useCheckPrices();
  const [prefill, setPrefill] = useState({ key: 0, name: '' });

  const open = (data ?? []).filter((e) => !e.bought);
  const bought = (data ?? []).filter((e) => e.bought);
  const total = open.reduce((sum, e) => sum + (Number(e.price) || 0), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <ShoppingBag className="h-6 w-6" />
          {t('title')}
        </h1>
        <p className="text-muted-foreground">{t('subtitle')}</p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t('form.title')}</CardTitle>
          <CardDescription>{t('form.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <AddForm key={prefill.key} initialName={prefill.name} />
        </CardContent>
      </Card>

      {gaps && gaps.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t('suggestions.title')}</CardTitle>
            <CardDescription>{t('suggestions.description')}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {gaps.map((gap) => (
              <Button
                key={gap.role}
                variant="outline"
                size="sm"
                onClick={() => setPrefill((p) => ({ key: p.key + 1, name: roleLabel(gap.role) }))}
              >
                <Plus className="mr-1 h-3 w-3" />
                {t('suggestions.item', { role: roleLabel(gap.role), have: gap.have, target: gap.target })}
              </Button>
            ))}
          </CardContent>
        </Card>
      )}

      {isLoading && <Skeleton className="h-40 w-full" />}

      {data && (
        <>
          <div className="flex items-baseline justify-between">
            <h2 className="text-lg font-semibold">{t('list.title', { count: open.length })}</h2>
            <div className="flex items-center gap-3">
              {total > 0 && (
                <span className="text-sm text-muted-foreground">
                  {t('list.total', { total: money(locale, String(total)) ?? '' })}
                </span>
              )}
              {open.some((e) => e.link) && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={checkPrices.isPending}
                  onClick={() =>
                    checkPrices.mutate(undefined, {
                      onSuccess: (entries) => {
                        const drops = entries.filter((e) => e.price_dropped_at).length;
                        toast.success(drops ? t('price.foundDrops', { count: drops }) : t('price.noDrops'));
                      },
                      onError: () => toast.error(t('error')),
                    })
                  }
                >
                  {checkPrices.isPending ? (
                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-1 h-3 w-3" />
                  )}
                  {t('price.check')}
                </Button>
              )}
            </div>
          </div>
          {open.length === 0 ? (
            <p className="py-6 text-center text-muted-foreground">{t('list.empty')}</p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {open.map((entry) => (
                <EntryCard key={entry.id} entry={entry} />
              ))}
            </div>
          )}
          {bought.length > 0 && (
            <>
              <h2 className="pt-4 text-lg font-semibold">{t('list.bought', { count: bought.length })}</h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {bought.map((entry) => (
                  <EntryCard key={entry.id} entry={entry} />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
