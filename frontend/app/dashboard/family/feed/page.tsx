'use client';

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import {
  Loader2,
  Users,
  Star,
  Shirt,
  ChevronRight,
  Settings,
  Calendar,
  Zap,
  Edit3,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';
import { useFamily } from '@/lib/hooks/use-family';
import { useFamilyOutfits, type Outfit, type OutfitSource } from '@/lib/hooks/use-outfits';
import { FamilyRatingForm, FamilyRatingsDisplay } from '@/components/family-ratings';
import { OutfitPreviewDialog } from '@/components/outfit-preview-dialog';
import Image from 'next/image';
import Link from 'next/link';

function getInitials(name: string) {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function SourceBadge({ source }: { source: OutfitSource }) {
  const config: Record<OutfitSource, { icon: typeof Calendar; label: string; className: string }> = {
    scheduled: {
      icon: Calendar,
      label: 'Scheduled',
      className: 'bg-primary/10 text-primary border-primary/20',
    },
    on_demand: {
      icon: Zap,
      label: 'On Demand',
      className: 'bg-orange-500/10 text-orange-600 border-orange-500/20',
    },
    manual: {
      icon: Edit3,
      label: 'Manual',
      className: 'bg-purple-500/10 text-purple-600 border-purple-500/20',
    },
    pairing: {
      icon: Zap,
      label: 'Pairing',
      className: 'bg-violet-500/10 text-violet-600 border-violet-500/20',
    },
  };

  const { icon: Icon, label, className } = config[source];

  return (
    <Badge variant="outline" className={className}>
      <Icon className="h-3 w-3 mr-1" />
      {label}
    </Badge>
  );
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
              {outfit.occasion}
            </Badge>
          </div>
          <span className="text-xs text-muted-foreground">
            {outfit.scheduled_for ? new Date(outfit.scheduled_for).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            }) : 'Lookbook'}
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
              ({outfit.family_rating_count} rating{outfit.family_rating_count !== 1 ? 's' : ''})
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
              Rate {memberName}&apos;s outfit
            </Button>
          )
        ) : (
          <div className="flex items-center justify-between pt-2 border-t">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Your rating:</span>
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
              Edit
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
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Family Feed</h1>
        <p className="text-muted-foreground">
          Browse and rate your family members&apos; outfits
        </p>
      </div>

      <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
        <div className="rounded-full bg-muted p-6 mb-4">
          <Users className="h-12 w-12 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold mb-2">Join a family first</h3>
        <p className="text-muted-foreground mb-6 max-w-sm">
          Create or join a family to browse and rate each other&apos;s outfits.
        </p>
        <Button asChild>
          <Link href="/dashboard/family">
            <Users className="mr-2 h-4 w-4" />
            Set Up Family
          </Link>
        </Button>
      </div>
    </div>
  );
}

function FeedContent() {
  const { data: session } = useSession();
  const { data: family, isLoading: familyLoading } = useFamily();
  const currentEmail = session?.user?.email;
  const currentMember = family?.members.find((m) => m.email === currentEmail);
  const otherMembers = family?.members.filter((m) => m.email !== currentEmail) ?? [];

  const [selectedMember, setSelectedMember] = useState<string | undefined>(undefined);
  const [previewOutfit, setPreviewOutfit] = useState<Outfit | null>(null);

  // Auto-select first member when family loads
  const activeMemberId = selectedMember ?? (otherMembers.length > 0 ? otherMembers[0].id : undefined);
  const { data, isLoading } = useFamilyOutfits(activeMemberId);

  const selectedMemberInfo = otherMembers.find((m) => m.id === activeMemberId);

  if (familyLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!family) {
    return <NoFamilyState />;
  }

  if (otherMembers.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Family Feed</h1>
            <p className="text-muted-foreground">
              Browse and rate your family members&apos; outfits
            </p>
          </div>
          <Button variant="outline" size="sm" asChild>
            <Link href="/dashboard/family">
              <Settings className="h-4 w-4 mr-2" />
              Manage Family
            </Link>
          </Button>
        </div>

        <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
          <div className="rounded-full bg-muted p-6 mb-4">
            <Users className="h-12 w-12 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold mb-2">No other members yet</h3>
          <p className="text-muted-foreground mb-6 max-w-sm">
            Invite family members to start browsing and rating each other&apos;s outfits.
          </p>
          <Button asChild>
            <Link href="/dashboard/family">
              Invite Members
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
          <h1 className="text-2xl font-bold tracking-tight">Family Feed</h1>
          <p className="text-muted-foreground">
            Browse and rate your family members&apos; outfits
          </p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/dashboard/family">
            <Settings className="h-4 w-4 mr-2" />
            Manage Family
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
          <h3 className="text-base font-semibold mb-1">No outfits yet</h3>
          <p className="text-sm text-muted-foreground max-w-xs">
            {selectedMemberInfo?.display_name ?? 'This member'} hasn&apos;t received any outfit recommendations yet.
            Check back later!
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.outfits.map((outfit) => (
            <FeedOutfitCard
              key={outfit.id}
              outfit={outfit}
              currentMemberId={currentMember?.id}
              memberName={selectedMemberInfo?.display_name.split(' ')[0] ?? 'their'}
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
