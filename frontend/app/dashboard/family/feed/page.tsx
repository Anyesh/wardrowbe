'use client';

import { useState } from 'react';
import {
  Loader2,
  Users,
  Star,
  Shirt,
  ChevronRight,
  Settings,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';
import { useCurrentFamilyMember, useFamily } from '@/lib/hooks/use-family';
import { useFamilyOutfits, type Outfit } from '@/lib/hooks/use-outfits';
import { useOccasionLabel } from '@/lib/hooks/use-translated-constants';
import { SourceBadge } from '@/components/shared/source-badge';
import { FamilyRatingForm, FamilyRatingsDisplay } from '@/components/family-ratings';
import { OutfitPreviewDialog } from '@/components/outfit-preview-dialog';
import Image from 'next/image';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { formatDate } from '@/lib/utils';

function getInitials(name: string) {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function FeedOutfitCard({
  outfit,
  currentMemberId,
  memberName,
  onPreview,
}: {
  outfit: Outfit;
  currentMemberId?: string;
  memberName: string;
  onPreview: () => void;
}) {
  const t = useTranslations('family');
  const tc = useTranslations('common');
  const occasionLabel = useOccasionLabel();
  const locale = useLocale();
  const [showRatingForm, setShowRatingForm] = useState(false);
  const myRating = outfit.family_ratings?.find((r) => r.user_id === currentMemberId);

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <SourceBadge source={outfit.source} />
            <Badge variant="secondary" className="capitalize text-xs">
              {occasionLabel(outfit.occasion)}
            </Badge>
          </div>
          <span className="text-xs text-muted-foreground">
            {outfit.scheduled_for
              ? formatDate(outfit.scheduled_for, locale, {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })
              : t('feed.lookbook')}
          </span>
        </div>

        {/* Item thumbnails - clickable */}
        <button
          type="button"
          onClick={onPreview}
          className="flex gap-2 text-left w-full group"
        >
          {outfit.items.map((item) => (
            <div
              key={item.id}
              className="w-20 h-20 rounded-lg bg-muted overflow-hidden relative border shadow-sm group-hover:shadow-md transition-shadow"
            >
              {item.thumbnail_url ? (
                <Image
                  src={item.thumbnail_url}
                  alt={item.name || item.type}
                  fill
                  className="object-cover"
                  sizes="80px"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">
                  {item.type}
                </div>
              )}
            </div>
          ))}
        </button>

        {/* AI reasoning */}
        {outfit.reasoning && (
          <p className="text-sm text-muted-foreground">{outfit.reasoning}</p>
        )}

        {/* Family ratings summary */}
        {outfit.family_rating_count != null && outfit.family_rating_count > 0 && (
          <div className="flex items-center gap-2 text-sm">
            <Users className="h-4 w-4 text-muted-foreground" />
            <div className="flex gap-0.5">
              {[1, 2, 3, 4, 5].map((star) => (
                <Star
                  key={star}
                  className={`h-4 w-4 ${
                    star <= Math.round(outfit.family_rating_average ?? 0)
                      ? 'fill-yellow-400 text-yellow-400'
                      : 'text-muted-foreground/30'
                  }`}
                />
              ))}
            </div>
            <span className="text-muted-foreground text-xs">
              {t('feed.ratingCount', { count: outfit.family_rating_count })}
            </span>
          </div>
        )}

        {/* All family ratings */}
        {outfit.family_ratings && outfit.family_ratings.length > 0 && (
          <FamilyRatingsDisplay
            ratings={outfit.family_ratings}
            outfitId={outfit.id}
            currentUserId={currentMemberId}
          />
        )}

        {/* Rating action */}
        {!myRating ? (
          showRatingForm ? (
            <div className="pt-2 border-t">
              <FamilyRatingForm
                outfitId={outfit.id}
                onSuccess={() => setShowRatingForm(false)}
              />
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="w-full"
              onClick={() => setShowRatingForm(true)}
            >
              <Star className="h-4 w-4 mr-2" />
              {t('feed.rateOutfit', { member: memberName })}
            </Button>
          )
        ) : (
          <div className="flex items-center justify-between pt-2 border-t">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">{t('ratings.yourRating')}</span>
              <div className="flex gap-0.5">
                {[1, 2, 3, 4, 5].map((star) => (
                  <Star
                    key={star}
                    className={`h-4 w-4 ${
                      star <= myRating.rating
                        ? 'fill-yellow-400 text-yellow-400'
                        : 'text-muted-foreground/30'
                    }`}
                  />
                ))}
              </div>
              {myRating.comment && (
                <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                  &ldquo;{myRating.comment}&rdquo;
                </span>
              )}
            </div>
            <Button
              size="sm"
              variant="ghost"
              className="text-xs"
              onClick={() => setShowRatingForm(!showRatingForm)}
            >
              {tc('edit')}
            </Button>
          </div>
        )}

        {/* Show edit form when editing existing rating */}
        {myRating && showRatingForm && (
          <div className="pt-2 border-t">
            <FamilyRatingForm
              outfitId={outfit.id}
              existingRating={myRating}
              onSuccess={() => setShowRatingForm(false)}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function NoFamilyState() {
  const t = useTranslations('family');
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t('feed.title')}</h1>
        <p className="text-muted-foreground">
          {t('feed.subtitle')}
        </p>
      </div>

      <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
        <div className="rounded-full bg-muted p-6 mb-4">
          <Users className="h-12 w-12 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold mb-2">{t('feed.noFamily.title')}</h3>
        <p className="text-muted-foreground mb-6 max-w-sm">
          {t('feed.noFamily.description')}
        </p>
        <Button asChild>
          <Link href="/dashboard/family">
            <Users className="mr-2 h-4 w-4" />
            {t('feed.noFamily.setUpFamily')}
          </Link>
        </Button>
      </div>
    </div>
  );
}

function FeedContent() {
  const t = useTranslations('family');
  const te = useTranslations('errors');
  const { data: family, isLoading: familyLoading } = useFamily();
  const {
    member: currentMember,
    isPending: memberPending,
    isError: memberError,
  } = useCurrentFamilyMember(family);
  // Until the current member is known, filtering on it would list the user among the others
  // and auto-select their own feed.
  const otherMembers =
    memberPending || memberError
      ? []
      : (family?.members.filter((m) => m.id !== currentMember?.id) ?? []);

  const [selectedMember, setSelectedMember] = useState<string | undefined>(undefined);
  const [previewOutfit, setPreviewOutfit] = useState<Outfit | null>(null);

  // Auto-select first member when family loads
  const activeMemberId = selectedMember ?? (otherMembers.length > 0 ? otherMembers[0].id : undefined);
  const { data, isLoading } = useFamilyOutfits(activeMemberId);

  const selectedMemberInfo = otherMembers.find((m) => m.id === activeMemberId);

  if (familyLoading || memberPending) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!family) {
    return <NoFamilyState />;
  }

  if (memberError) {
    return <div className="text-center py-8 text-red-500">{te('pageLoad.title')}</div>;
  }

  if (otherMembers.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{t('feed.title')}</h1>
            <p className="text-muted-foreground">
              {t('feed.subtitle')}
            </p>
          </div>
          <Button variant="outline" size="sm" asChild>
            <Link href="/dashboard/family">
              <Settings className="h-4 w-4 mr-2" />
              {t('feed.noMembers.manageFamily')}
            </Link>
          </Button>
        </div>

        <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
          <div className="rounded-full bg-muted p-6 mb-4">
            <Users className="h-12 w-12 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold mb-2">{t('feed.noMembers.title')}</h3>
          <p className="text-muted-foreground mb-6 max-w-sm">
            {t('feed.noMembers.description')}
          </p>
          <Button asChild>
            <Link href="/dashboard/family">
              {t('feed.noMembers.inviteMembers')}
            </Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t('feed.title')}</h1>
          <p className="text-muted-foreground">
            {t('feed.subtitle')}
          </p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/dashboard/family">
            <Settings className="h-4 w-4 mr-2" />
            {t('feed.noMembers.manageFamily')}
          </Link>
        </Button>
      </div>

      {/* Member selector */}
      <div className="flex gap-3 overflow-x-auto pb-2">
        {otherMembers.map((member) => (
          <button
            key={member.id}
            type="button"
            onClick={() => setSelectedMember(member.id)}
            className={`flex flex-col items-center gap-1.5 p-3 rounded-xl border-2 transition-all flex-shrink-0 min-w-[80px] ${
              activeMemberId === member.id
                ? 'border-primary bg-primary/5 shadow-sm'
                : 'border-transparent hover:border-muted-foreground/20 hover:bg-muted/50'
            }`}
          >
            <Avatar className="h-12 w-12">
              <AvatarImage src={member.avatar_url} />
              <AvatarFallback>{getInitials(member.display_name)}</AvatarFallback>
            </Avatar>
            <span className={`text-xs font-medium truncate max-w-[72px] ${
              activeMemberId === member.id ? 'text-primary' : 'text-muted-foreground'
            }`}>
              {member.display_name.split(' ')[0]}
            </span>
          </button>
        ))}
      </div>

      {/* Outfits feed */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="p-4 space-y-3">
                <div className="flex gap-2">
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-5 w-16" />
                </div>
                <div className="flex gap-2">
                  <Skeleton className="h-20 w-20 rounded-lg" />
                  <Skeleton className="h-20 w-20 rounded-lg" />
                  <Skeleton className="h-20 w-20 rounded-lg" />
                </div>
                <Skeleton className="h-9 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : !data || data.outfits.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
          <Shirt className="h-10 w-10 text-muted-foreground mb-3" />
          <h3 className="text-base font-semibold mb-1">{t('feed.noOutfits.title')}</h3>
          <p className="text-sm text-muted-foreground max-w-xs">
            {t('feed.noOutfits.description', { member: selectedMemberInfo?.display_name ?? t('feed.unknownMember') })}
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.outfits.map((outfit) => (
            <FeedOutfitCard
              key={outfit.id}
              outfit={outfit}
              currentMemberId={currentMember?.id}
              memberName={selectedMemberInfo?.display_name.split(' ')[0] ?? t('feed.unknownMemberShort')}
              onPreview={() => setPreviewOutfit(outfit)}
            />
          ))}
        </div>
      )}

      {/* Preview dialog */}
      {previewOutfit && (
        <OutfitPreviewDialog
          outfit={previewOutfit}
          open={!!previewOutfit}
          onClose={() => setPreviewOutfit(null)}
          isOwner={false}
        />
      )}
    </div>
  );
}

export default function FamilyFeedPage() {
  return <FeedContent />;
}
