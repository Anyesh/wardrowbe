'use client';

import { useState } from 'react';
import { Sparkles, Layers } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { usePairings } from '@/lib/hooks/use-pairings';
import { useItemTypes } from '@/lib/hooks/use-items';
import { PairingCard } from '@/components/pairing-card';
import { FeedbackDialog } from '@/components/feedback-dialog';
import { OutfitPreviewDialog } from '@/components/outfit-preview-dialog';
import { useI18n } from '@/lib/i18n';
import { Pairing } from '@/lib/types';
import { Outfit } from '@/lib/hooks/use-outfits';

function EmptyPairings() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="rounded-full bg-muted p-6 mb-4">
        <Layers className="h-12 w-12 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold mb-2">{t('pairings.empty')}</h3>
      <p className="text-muted-foreground mb-6 max-w-sm">
        {t('pairings.emptyHint')}
      </p>
      <Button variant="outline" asChild>
        <a href="/dashboard/wardrobe">{t('pairings.goToWardrobe')}</a>
      </Button>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <Card key={i}>
          <CardContent className="p-4">
            <div className="flex items-start justify-between mb-3">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-5 w-5" />
            </div>
            <div className="flex items-center gap-2 p-2 rounded-lg bg-muted mb-3">
              <Skeleton className="w-12 h-12 rounded-md" />
              <div className="flex-1">
                <Skeleton className="h-4 w-20 mb-1" />
                <Skeleton className="h-3 w-16" />
              </div>
            </div>
            <div className="flex gap-2">
              {[1, 2, 3].map((j) => (
                <Skeleton key={j} className="w-14 h-14 rounded" />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function PairingsPage() {
  const { t } = useI18n();
  const [page, setPage] = useState(1);
  const [sourceType, setSourceType] = useState<string | undefined>(undefined);
  const [feedbackOutfit, setFeedbackOutfit] = useState<Outfit | null>(null);
  const [previewOutfit, setPreviewOutfit] = useState<Outfit | null>(null);

  const { data, isLoading, isError } = usePairings(page, 20, sourceType);
  const { data: itemTypes } = useItemTypes();

  const handleSourceTypeChange = (value: string) => {
    setSourceType(value === 'all' ? undefined : value);
    setPage(1);
  };

  if (isError) {
    return (
      <div className="text-center py-8 text-red-500">
        {t('pairings.loadFailed')}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-primary" />
            {t('pairings.title')}
          </h1>
          <p className="text-muted-foreground">{t('pairings.subtitle')}</p>
        </div>
      </div>

      <div className="flex gap-3 flex-wrap items-center">
        <Select value={sourceType || 'all'} onValueChange={handleSourceTypeChange}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder={t('pairings.allTypes')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('pairings.allTypes')}</SelectItem>
            {itemTypes?.map((type) => (
              <SelectItem key={type.type} value={type.type}>
                {type.type} ({type.count})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {data && (
          <p className="text-sm text-muted-foreground">
            {data.total} pairing{data.total !== 1 ? 's' : ''}
          </p>
        )}
      </div>

      {isLoading ? (
        <LoadingSkeleton />
      ) : !data || data.pairings.length === 0 ? (
        <EmptyPairings />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {data.pairings.map((pairing) => (
              <PairingCard
                key={pairing.id}
                pairing={pairing}
                onFeedback={() => setFeedbackOutfit(pairing as unknown as Outfit)}
                onPreview={() => setPreviewOutfit(pairing as unknown as Outfit)}
              />
            ))}
          </div>

          {data.has_more && (
            <div className="flex justify-center pt-4">
              <Button
                variant="outline"
                onClick={() => setPage((p) => p + 1)}
              >
                {t('common.loadMore')}
              </Button>
            </div>
          )}
        </>
      )}

      {feedbackOutfit && (
        <FeedbackDialog
          outfit={feedbackOutfit}
          open={!!feedbackOutfit}
          onClose={() => setFeedbackOutfit(null)}
        />
      )}

      {previewOutfit && (
        <OutfitPreviewDialog
          outfit={previewOutfit}
          open={!!previewOutfit}
          onClose={() => setPreviewOutfit(null)}
        />
      )}
    </div>
  );
}