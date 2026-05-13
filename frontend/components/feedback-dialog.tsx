'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Star, Check, X, ChevronLeft, Search, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { useSubmitFeedback, type Outfit } from '@/lib/hooks/use-outfits';
import { useItems } from '@/lib/hooks/use-items';
import { cn } from '@/lib/utils';
import Image from 'next/image';
import { useTranslations } from 'next-intl';

function StarRating({
  rating,
  onRate,
  size = 'sm',
}: {
  rating: number;
  onRate?: (rating: number) => void;
  size?: 'sm' | 'lg';
}) {
  const sizeClass = size === 'lg' ? 'h-6 w-6' : 'h-4 w-4';

  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          onClick={() => onRate?.(star)}
          disabled={!onRate}
          className={onRate ? 'cursor-pointer hover:scale-110 transition-transform' : 'cursor-default'}
        >
          <Star
            className={`${sizeClass} ${star <= rating ? 'fill-yellow-400 text-yellow-400' : 'text-muted-foreground'}`}
          />
        </button>
      ))}
    </div>
  );
}

interface FeedbackDialogProps {
  outfit: Outfit;
  open: boolean;
  onClose: () => void;
}

type FeedbackStep = 'wear-question' | 'rating' | 'wore-instead';

const PAGE_SIZE = 24;

interface AccumulatedItem {
  id: string;
  name?: string;
  type: string;
  thumbnail_path?: string;
  thumbnail_url?: string;
  image_path: string;
  image_url?: string;
  is_archived: boolean;
}

export function FeedbackDialog({ outfit, open, onClose }: FeedbackDialogProps) {
  const t = useTranslations('dialogs.feedback');
  const [step, setStep] = useState<FeedbackStep>('wear-question');
  const [actuallyWorn, setActuallyWorn] = useState<boolean | null>(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [selectedItems, setSelectedItems] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [accumulatedItems, setAccumulatedItems] = useState<AccumulatedItem[]>([]);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const submitFeedback = useSubmitFeedback();

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(1); // Reset to first page on search
      setAccumulatedItems([]); // Clear accumulated items on new search
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Fetch wardrobe items with search and pagination
  const { data: itemsData, isLoading, isFetching } = useItems(
    { search: debouncedSearch || undefined, is_archived: false },
    page,
    PAGE_SIZE
  );
  const hasMore = itemsData?.has_more ?? false;
  const totalItems = itemsData?.total ?? 0;

  // Accumulate items as pages load
  useEffect(() => {
    if (itemsData?.items) {
      if (page === 1) {
        setAccumulatedItems(itemsData.items);
      } else {
        setAccumulatedItems((prev) => {
          const existingIds = new Set(prev.map((i) => i.id));
          const newItems = itemsData.items.filter((i) => !existingIds.has(i.id));
          return [...prev, ...newItems];
        });
      }
    }
  }, [itemsData?.items, page]);

  // Use accumulated items for display
  const wardrobeItems = accumulatedItems;

  // Reset state when dialog opens for a different outfit
  useEffect(() => {
    if (open) {
      // Check if feedback already exists
      const hasFeedback = outfit.feedback?.rating != null;

      if (hasFeedback) {
        // Go straight to rating step if already has feedback
        setStep('rating');
        setActuallyWorn(true);
      } else {
        // Start with wear question
        setStep('wear-question');
        setActuallyWorn(null);
      }

      setRating(outfit.feedback?.rating ?? 0);
      setComment(outfit.feedback?.comment ?? '');
      setSelectedItems([]);
      setSearchQuery('');
      setDebouncedSearch('');
      setPage(1);
      setAccumulatedItems([]);
    }
  }, [open, outfit.id, outfit.feedback]);

  // Load more items for infinite scroll
  const loadMore = useCallback(() => {
    if (hasMore && !isFetching) {
      setPage((p) => p + 1);
    }
  }, [hasMore, isFetching]);

  // Handle scroll for infinite loading
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const target = e.target as HTMLDivElement;
    const nearBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + 100;
    if (nearBottom) {
      loadMore();
    }
  }, [loadMore]);

  const handleWearAnswer = (wore: boolean) => {
    setActuallyWorn(wore);
    if (wore) {
      setStep('rating');
    } else {
      setStep('wore-instead');
    }
  };

  const toggleItemSelection = (itemId: string) => {
    setSelectedItems((prev) =>
      prev.includes(itemId) ? prev.filter((id) => id !== itemId) : [...prev, itemId]
    );
  };

  const handleSubmit = async () => {
    try {
      await submitFeedback.mutateAsync({
        outfitId: outfit.id,
        feedback: {
          rating: rating > 0 ? rating : undefined,
          comment: comment.trim() || undefined,
          worn: actuallyWorn === true || undefined,
          actually_worn: actuallyWorn ?? undefined,
          wore_instead_items: selectedItems.length > 0 ? selectedItems : undefined,
        },
      });
      toast.success(t('submitted'));
      onClose();
    } catch {
      toast.error(t('submitError'));
    }
  };

  const handleSkipWoreInstead = async () => {
    try {
      await submitFeedback.mutateAsync({
        outfitId: outfit.id,
        feedback: {
          actually_worn: false,
        },
      });
      toast.success(t('submitted'));
      onClose();
    } catch {
      toast.error(t('submitError'));
    }
  };

  // Get items from the outfit to exclude from "wore instead" picker
  const outfitItemIds = new Set(outfit.items?.map((i) => i.id) || []);

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-md">
        {/* Step 1: Did you wear this? */}
        {step === 'wear-question' && (
          <>
            <DialogHeader>
              <DialogTitle>{t('didYouWear')}</DialogTitle>
              <DialogDescription>
                {t('didYouWearDesc')}
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-3 py-4">
              <Button
                variant="outline"
                size="lg"
                className="h-16 justify-start gap-3"
                onClick={() => handleWearAnswer(true)}
              >
                <div className="rounded-full bg-green-100 dark:bg-green-900/30 p-2">
                  <Check className="h-5 w-5 text-green-600 dark:text-green-400" />
                </div>
                <div className="text-left">
                  <div className="font-medium">{t('yesWoreIt')}</div>
                  <div className="text-sm text-muted-foreground">{t('rateHowItWent')}</div>
                </div>
              </Button>
              <Button
                variant="outline"
                size="lg"
                className="h-16 justify-start gap-3"
                onClick={() => handleWearAnswer(false)}
              >
                <div className="rounded-full bg-orange-100 dark:bg-orange-900/30 p-2">
                  <X className="h-5 w-5 text-orange-600 dark:text-orange-400" />
                </div>
                <div className="text-left">
                  <div className="font-medium">{t('noWoreSomethingElse')}</div>
                  <div className="text-sm text-muted-foreground">{t('tellUsWhatYouWore')}</div>
                </div>
              </Button>
            </div>
          </>
        )}

        {/* Step 2a: Rating (if they wore it) */}
        {step === 'rating' && (
          <>
            <DialogHeader>
              <DialogTitle>{t('rateThisOutfit')}</DialogTitle>
              <DialogDescription>{t('howDidItWork')}</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div>
                <label className="text-sm font-medium mb-2 block">{t('overallRating')}</label>
                <StarRating rating={rating} onRate={setRating} size="lg" />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">{t('commentsOptional')}</label>
                <Textarea
                  placeholder={t('commentsPlaceholder')}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
              </div>
            </div>
            <div className="flex justify-between">
              {!outfit.feedback?.rating && (
                <Button variant="ghost" onClick={() => setStep('wear-question')}>
                  <ChevronLeft className="h-4 w-4 mr-1" />
                  {t('back')}
                </Button>
              )}
              <div className="flex gap-2 ml-auto">
                <Button variant="outline" onClick={onClose}>
                  {t('cancel')}
                </Button>
                <Button onClick={handleSubmit} disabled={submitFeedback.isPending}>
                  {submitFeedback.isPending ? t('submitting') : t('submit')}
                </Button>
              </div>
            </div>
          </>
        )}

        {/* Step 2b: What did you wear instead? */}
        {step === 'wore-instead' && (
          <>
            <DialogHeader>
              <DialogTitle>{t('whatDidYouWear')}</DialogTitle>
              <DialogDescription>
                {t('whatDidYouWearDesc')}
              </DialogDescription>
            </DialogHeader>

            {/* Search input */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={t('searchWardrobe')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>

            {/* Items grid with scroll */}
            <div
              ref={scrollContainerRef}
              onScroll={handleScroll}
              className="h-[280px] overflow-y-auto py-2 -mx-2 px-2"
            >
              {/* Selected items count */}
              {selectedItems.length > 0 && (
                <div className="text-xs text-muted-foreground mb-2">
                  {t('itemsSelected', { count: selectedItems.length })}
                </div>
              )}

              <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                {wardrobeItems
                  .filter((item) => !outfitItemIds.has(item.id))
                  .map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => toggleItemSelection(item.id)}
                      className={cn(
                        'relative aspect-square rounded-lg overflow-hidden border-2 transition-all',
                        selectedItems.includes(item.id)
                          ? 'border-primary ring-2 ring-primary/20'
                          : 'border-border hover:border-muted-foreground/50'
                      )}
                    >
                      <Image
                        src={item.thumbnail_url || item.image_url || item.image_path}
                        alt={item.name || item.type}
                        fill
                        className="object-cover"
                        sizes="(max-width: 640px) 33vw, 25vw"
                        loading="lazy"
                      />
                      {selectedItems.includes(item.id) && (
                        <div className="absolute inset-0 bg-primary/30 flex items-center justify-center">
                          <div className="rounded-full bg-primary p-1.5 shadow-lg">
                            <Check className="h-4 w-4 text-primary-foreground" />
                          </div>
                        </div>
                      )}
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-1.5">
                        <span className="text-[10px] sm:text-xs text-white font-medium truncate block">
                          {item.name || item.type}
                        </span>
                      </div>
                    </button>
                  ))}
              </div>

              {/* Loading states */}
              {isLoading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              )}

              {/* Load more indicator */}
              {isFetching && !isLoading && (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mr-2" />
                  <span className="text-xs text-muted-foreground">{t('loadingMore')}</span>
                </div>
              )}

              {/* Empty state */}
              {!isLoading && wardrobeItems.length === 0 && (
                <div className="text-center text-muted-foreground py-8">
                  {debouncedSearch ? t('noMatch') : t('noItemsInWardrobe')}
                </div>
              )}

              {/* End of results */}
              {!isLoading && !hasMore && wardrobeItems.length > 0 && (
                <div className="text-center text-xs text-muted-foreground py-3">
                  {t('showingAll', { count: totalItems })}
                </div>
              )}
            </div>

            <div className="flex justify-between pt-2 border-t">
              <Button variant="ghost" onClick={() => setStep('wear-question')}>
                <ChevronLeft className="h-4 w-4 mr-1" />
                {t('back')}
              </Button>
              <div className="flex gap-2">
                <Button variant="outline" onClick={handleSkipWoreInstead}>
                  {t('skip')}
                </Button>
                <Button
                  onClick={handleSubmit}
                  disabled={submitFeedback.isPending || selectedItems.length === 0}
                >
                  {submitFeedback.isPending
                    ? t('submitting')
                    : t('submitWithCount', { count: selectedItems.length })}
                </Button>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
