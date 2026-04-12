'use client';

import { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useParams, useRouter } from 'next/navigation';
import { format, formatDistanceToNow, parseISO } from 'date-fns';
import {
  BookmarkPlus,
  CalendarPlus,
  ChevronLeft,
  Loader2,
  Pencil,
  Star,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { LineageCard } from '@/components/shared/lineage-card';
import { CloneToLookbookDialog } from '@/components/shared/clone-to-lookbook-dialog';
import { useDeleteOutfit, useOutfit, useOutfits } from '@/lib/hooks/use-outfits';
import { useWearToday } from '@/lib/hooks/use-studio';
import { getErrorMessage } from '@/lib/api';

export default function OutfitDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const outfitId = params?.id;

  const { data: outfit, isLoading } = useOutfit(outfitId);
  const deleteMutation = useDeleteOutfit();
  const wearTodayMutation = useWearToday(outfitId ?? '');

  const [cloneDialogOpen, setCloneDialogOpen] = useState(false);

  const isTemplate =
    outfit !== undefined && outfit !== null && outfit.scheduled_for === null;
  const isWorn = !!outfit?.feedback?.worn_at;

  const { data: wearInstancesData } = useOutfits(
    isTemplate && outfitId ? { cloned_from_outfit_id: outfitId } : {},
    1,
    10
  );

  if (isLoading || !outfit) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const handleWearToday = async () => {
    try {
      const result = await wearTodayMutation.mutateAsync({});
      toast.success('Added to today');
      router.push(`/dashboard/outfits/${result.id}`);
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to wear today'));
    }
  };

  const handleDelete = async () => {
    if (!confirm('Delete this outfit? This cannot be undone.')) return;
    try {
      await deleteMutation.mutateAsync(outfit.id);
      toast.success('Outfit deleted');
      router.push('/dashboard/outfits');
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to delete'));
    }
  };

  const title = outfit.name || `${outfit.occasion} outfit`;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between gap-4">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/dashboard/outfits">
            <ChevronLeft className="h-4 w-4 mr-1" />
            Back to Outfits
          </Link>
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-bold tracking-tight capitalize">{title}</h1>
        <div className="flex items-center gap-2 mt-2">
          <Badge variant="outline" className="capitalize">
            {outfit.occasion}
          </Badge>
          <Badge variant="outline" className="capitalize">
            {outfit.source.replace('_', ' ')}
          </Badge>
          <span className="text-sm text-muted-foreground">
            {outfit.scheduled_for
              ? formatDistanceToNow(parseISO(outfit.scheduled_for), {
                  addSuffix: true,
                })
              : 'Lookbook template'}
          </span>
        </div>
      </div>

      <LineageCard outfit={outfit} />

      <Card>
        <CardContent className="p-4">
          <h2 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wide">
            Items ({outfit.items.length})
          </h2>
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-3">
            {outfit.items.map((item) => (
              <Link
                key={item.id}
                href={`/dashboard/wardrobe?itemId=${item.id}`}
                className="group"
              >
                <div className="relative aspect-square rounded-lg overflow-hidden border bg-muted">
                  {item.thumbnail_url || item.image_url ? (
                    <Image
                      src={(item.thumbnail_url || item.image_url)!}
                      alt={item.name || item.type}
                      fill
                      className="object-cover transition-transform group-hover:scale-105"
                      sizes="(max-width: 640px) 33vw, 20vw"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <span className="text-xs text-muted-foreground">
                        {item.type}
                      </span>
                    </div>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-1 truncate">
                  {item.name || item.type}
                </p>
              </Link>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        {isTemplate && (
          <Button onClick={handleWearToday} disabled={wearTodayMutation.isPending}>
            {wearTodayMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <CalendarPlus className="h-4 w-4 mr-2" />
            )}
            Wear today
          </Button>
        )}
        {!isTemplate && (
          <Button variant="outline" onClick={() => setCloneDialogOpen(true)}>
            <BookmarkPlus className="h-4 w-4 mr-2" />
            Save to lookbook
          </Button>
        )}
        {!isWorn && (
          <Button variant="outline" asChild>
            <Link href={`/dashboard/outfits/new?edit=${outfit.id}`}>
              <Pencil className="h-4 w-4 mr-2" />
              Edit
            </Link>
          </Button>
        )}
        <Button
          variant="outline"
          className="text-destructive hover:text-destructive"
          onClick={handleDelete}
          disabled={deleteMutation.isPending}
        >
          <Trash2 className="h-4 w-4 mr-2" />
          Delete
        </Button>
      </div>

      {isTemplate && wearInstancesData && wearInstancesData.total > 0 && (
        <Card>
          <CardContent className="p-4">
            <h2 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wide">
              Worn {wearInstancesData.total} time
              {wearInstancesData.total === 1 ? '' : 's'}
            </h2>
            <div className="space-y-2">
              {wearInstancesData.outfits.map((wear) => (
                <Link
                  key={wear.id}
                  href={`/dashboard/outfits/${wear.id}`}
                  className="flex items-center justify-between rounded-lg border px-3 py-2 hover:bg-muted/50"
                >
                  <span className="text-sm">
                    {wear.scheduled_for
                      ? format(parseISO(wear.scheduled_for), 'MMM d, yyyy')
                      : 'Undated'}
                  </span>
                  {wear.feedback?.rating && (
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Star className="h-3 w-3 fill-yellow-400 text-yellow-400" />
                      {wear.feedback.rating}
                    </div>
                  )}
                </Link>
              ))}
            </div>
            {wearInstancesData.has_more && (
              <Button variant="link" size="sm" asChild className="mt-2 px-0">
                <Link href={`/dashboard/outfits?filter=worn&cloned_from=${outfit.id}`}>
                  See all
                </Link>
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {isTemplate && wearInstancesData && wearInstancesData.total === 0 && (
        <Alert className="border-muted">
          <AlertDescription className="text-sm text-muted-foreground">
            This look has not been worn yet. Click &quot;Wear today&quot; to log it.
          </AlertDescription>
        </Alert>
      )}

      {!isTemplate && (
        <CloneToLookbookDialog
          open={cloneDialogOpen}
          sourceOutfitId={outfit.id}
          sourceOccasion={outfit.occasion}
          onClose={() => setCloneDialogOpen(false)}
          onSuccess={(newId) => router.push(`/dashboard/outfits/${newId}`)}
        />
      )}
    </div>
  );
}
