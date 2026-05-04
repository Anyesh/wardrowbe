'use client';

import { useState } from 'react';
import { Star, Loader2, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { toast } from 'sonner';
import { useSubmitFamilyRating, useDeleteFamilyRating } from '@/lib/hooks/use-outfits';
import { FamilyRating } from '@/lib/types';

function StarPicker({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const [hovered, setHovered] = useState(0);

  return (
    <div className="flex gap-1" onMouseLeave={() => setHovered(0)}>
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          onMouseEnter={() => setHovered(star)}
          onClick={() => onChange(star)}
          className="focus:outline-none"
        >
          <Star
            className={`h-6 w-6 transition-colors ${
              star <= (hovered || value)
                ? 'fill-yellow-400 text-yellow-400'
                : 'text-muted-foreground/30 hover:text-muted-foreground/50'
            }`}
          />
        </button>
      ))}
    </div>
  );
}

interface FamilyRatingFormProps {
  outfitId: string;
  existingRating?: FamilyRating;
  onSuccess?: () => void;
}

export function FamilyRatingForm({ outfitId, existingRating, onSuccess }: FamilyRatingFormProps) {
  const [rating, setRating] = useState(existingRating?.rating ?? 0);
  const [comment, setComment] = useState(existingRating?.comment ?? '');
  const submitRating = useSubmitFamilyRating();

  const handleSubmit = async () => {
    if (rating === 0) {
      toast.error('请先选择评分');
      return;
    }
    try {
      await submitRating.mutateAsync({
        outfitId,
        rating,
        comment: comment.trim() || undefined,
      });
      toast.success(existingRating ? '评分已更新！' : '评分已提交！');
      onSuccess?.();
    } catch {
      toast.error('提交评分失败');
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium">Your rating:</span>
        <StarPicker value={rating} onChange={setRating} />
      </div>
      <Textarea
        placeholder="Add a comment (optional)"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        rows={2}
        maxLength={500}
        className="resize-none text-sm"
      />
      <Button
        size="sm"
        onClick={handleSubmit}
        disabled={rating === 0 || submitRating.isPending}
      >
        {submitRating.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        {existingRating ? '更新评分' : '提交评分'}
      </Button>
    </div>
  );
}

function getInitials(name: string) {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

interface FamilyRatingsDisplayProps {
  ratings: FamilyRating[];
  outfitId: string;
  currentUserId?: string;
}

export function FamilyRatingsDisplay({ ratings, outfitId, currentUserId }: FamilyRatingsDisplayProps) {
  const deleteRating = useDeleteFamilyRating();

  if (ratings.length === 0) return null;

  const handleDelete = async () => {
    try {
      await deleteRating.mutateAsync(outfitId);
      toast.success('评分已移除');
    } catch {
      toast.error('移除评分失败');
    }
  };

  return (
    <div className="space-y-3">
      {ratings.map((r) => (
        <div key={r.id} className="flex items-start gap-3 p-2 rounded-lg bg-muted/50">
          <Avatar className="h-8 w-8">
            <AvatarImage src={r.user_avatar_url} />
            <AvatarFallback className="text-xs">
              {getInitials(r.user_display_name)}
            </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium truncate">{r.user_display_name}</span>
              <div className="flex gap-0.5">
                {[1, 2, 3, 4, 5].map((star) => (
                  <Star
                    key={star}
                    className={`h-3.5 w-3.5 ${
                      star <= r.rating
                        ? 'fill-yellow-400 text-yellow-400'
                        : 'text-muted-foreground/30'
                    }`}
                  />
                ))}
              </div>
            </div>
            {r.comment && (
              <p className="text-xs text-muted-foreground mt-0.5">&ldquo;{r.comment}&rdquo;</p>
            )}
          </div>
          {currentUserId && r.user_id === currentUserId && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-destructive"
              onClick={handleDelete}
              disabled={deleteRating.isPending}
            >
              {deleteRating.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}
