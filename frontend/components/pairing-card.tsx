'use client';

import { Trash2, Star, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { useDeletePairing } from '@/lib/hooks/use-pairings';
import { Pairing } from '@/lib/types';
import Image from 'next/image';

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => (
        <Star
          key={star}
          className={`h-3.5 w-3.5 ${
            star <= rating ? 'fill-yellow-400 text-yellow-400' : 'text-muted-foreground/30'
          }`}
        />
      ))}
    </div>
  );
}

interface PairingCardProps {
  pairing: Pairing;
  onFeedback?: () => void;
  onPreview?: () => void;
}

export function PairingCard({ pairing, onFeedback, onPreview }: PairingCardProps) {
  const deletePairing = useDeletePairing();

  const handleDelete = async () => {
    try {
      await deletePairing.mutateAsync(pairing.id);
      toast.success('Pairing deleted');
    } catch {
      toast.error('Failed to delete pairing');
    }
  };

  // Find the source item in the items list
  const sourceItemId = pairing.source_item?.id;
  const sourceItemInList = pairing.items.find((item) => item.id === sourceItemId);
  const otherItems = pairing.items.filter((item) => item.id !== sourceItemId);

  return (
    <Card className="overflow-hidden h-full flex flex-col">
      <CardContent className="p-3 flex flex-col flex-1">
        {/* Header with source badge */}
        <div className="flex items-center justify-between mb-2">
          <Badge variant="outline">
            <Sparkles className="h-3 w-3 mr-1" />
            Pairing
          </Badge>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-destructive"
            onClick={handleDelete}
            disabled={deletePairing.isPending}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* Source item highlighted */}
        {pairing.source_item && (
          <div className="mb-2">
            <p className="text-xs text-muted-foreground mb-1">Built around:</p>
            <div className="flex items-center gap-2 p-2 rounded-lg bg-primary/5 border border-primary/20">
              <div className="w-12 h-12 rounded-md bg-muted overflow-hidden relative border-2 border-primary/30">
                {pairing.source_item.thumbnail_url ? (
                  <Image
                    src={pairing.source_item.thumbnail_url}
                    alt={pairing.source_item.name || pairing.source_item.type}
                    fill
                    className="object-cover"
                    sizes="48px"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">
                    {pairing.source_item.type}
                  </div>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {pairing.source_item.name || pairing.source_item.type}
                </p>
                {pairing.source_item.primary_color && (
                  <p className="text-xs text-muted-foreground capitalize">
                    {pairing.source_item.primary_color}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Other items in outfit */}
        <button
          type="button"
          onClick={onPreview}
          className="flex gap-2 text-left w-full group"
        >
          {otherItems.map((item) => (
            <div
              key={item.id}
              className="w-14 h-14 rounded-lg bg-muted overflow-hidden relative border shadow-sm group-hover:shadow-md transition-shadow"
            >
              {item.thumbnail_url ? (
                <Image
                  src={item.thumbnail_url}
                  alt={item.name || item.type}
                  fill
                  className="object-cover"
                  sizes="56px"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">
                  {item.type}
                </div>
              )}
            </div>
          ))}
        </button>

        {/* Feedback display */}
        {pairing.feedback && (pairing.feedback.rating || pairing.feedback.comment) && (
          <div className="mt-2 pt-2 border-t">
            <div className="flex items-center gap-2">
              {pairing.feedback.rating && (
                <StarRating rating={pairing.feedback.rating} />
              )}
              {pairing.feedback.comment && (
                <p className="text-xs text-muted-foreground truncate flex-1">
                  &ldquo;{pairing.feedback.comment}&rdquo;
                </p>
              )}
            </div>
          </div>
        )}

        {/* AI reasoning */}
        {(pairing.reasoning || pairing.highlights) && (
          <div className="mt-2 space-y-1.5 text-xs flex-1">
            {pairing.reasoning && (
              <p className="font-medium text-foreground break-words">{pairing.reasoning}</p>
            )}
            {pairing.highlights && pairing.highlights.length > 0 && (
              <ul className="space-y-0.5">
                {pairing.highlights.slice(0, 3).map((highlight, index) => (
                  <li key={index} className="flex items-start gap-1.5 text-muted-foreground">
                    <span className="text-primary mt-0.5">•</span>
                    <span className="line-clamp-2">{highlight}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Styling tip */}
        {pairing.style_notes && (
          <div className="mt-2 p-2 bg-muted rounded border text-xs">
            <p className="text-muted-foreground break-words">
              <span className="font-medium text-foreground">Tip:</span> {pairing.style_notes}
            </p>
          </div>
        )}

        {/* Feedback button */}
        {pairing.status === 'accepted' && onFeedback && (
          <div className="mt-auto pt-3">
            <Button
              size="sm"
              variant="outline"
              className="w-full h-8 text-xs"
              onClick={onFeedback}
            >
              <Star className="h-3 w-3 mr-1" />
              {pairing.feedback?.rating ? 'Update Rating' : 'Rate This Pairing'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
