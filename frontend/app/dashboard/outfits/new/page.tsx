'use client';

import { useCallback, useEffect, useMemo, useReducer, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, AlertTriangle, ChevronLeft, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { CanvasPanel } from '@/components/studio/canvas-panel';
import { DetailsPanel } from '@/components/studio/details-panel';
import { ItemPicker } from '@/components/shared/item-picker';
import { CloneToLookbookDialog } from '@/components/shared/clone-to-lookbook-dialog';
import { ApiError, getErrorMessage } from '@/lib/api';
import { useItems } from '@/lib/hooks/use-items';
import { useOutfit } from '@/lib/hooks/use-outfits';
import { useCreateStudioOutfit, usePatchOutfit } from '@/lib/hooks/use-studio';
import {
  INITIAL_STUDIO_STATE,
  studioReducer,
  type StudioItem,
} from '@/lib/studio/editor-state';
import {
  clearDraft,
  loadDraft,
  saveDraft,
  type StudioDraft,
} from '@/lib/studio/draft-storage';
import { isWornImmutableError } from '@/lib/studio/errors';
import { computeEditLoadPhase } from '@/lib/studio/edit-load';

export default function StudioEditorPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const editId = searchParams.get('edit') || undefined;
  const isEditMode = !!editId;

  const [state, dispatch] = useReducer(studioReducer, INITIAL_STUDIO_STATE);
  const [draftPrompted, setDraftPrompted] = useState(false);
  const [pendingDraft, setPendingDraft] = useState<StudioDraft | null>(null);
  const [editLoaded, setEditLoaded] = useState(false);
  const [wornConflictOpen, setWornConflictOpen] = useState(false);
  const [cloneDialogOpen, setCloneDialogOpen] = useState(false);

  const createMutation = useCreateStudioOutfit();
  const patchMutation = usePatchOutfit();

  const {
    data: editOutfit,
    isLoading: editLoading,
    isError: editIsError,
    error: editError,
    refetch: refetchEdit,
  } = useOutfit(editId);

  const editErrorStatus =
    editError instanceof ApiError ? editError.status : null;
  const editOutfitIsWorn = !!editOutfit?.feedback?.worn_at;

  useEffect(() => {
    if (!isEditMode || editLoaded || !editOutfit) return;
    if (editOutfit.feedback?.worn_at) return;
    const items: StudioItem[] = editOutfit.items.map((item) => ({
      id: item.id,
      type: item.type,
      name: item.name ?? null,
      thumbnail_url: item.thumbnail_url ?? null,
      image_url: item.image_url ?? null,
      primary_color: item.primary_color ?? null,
    }));
    dispatch({
      type: 'LOAD',
      state: {
        items,
        name: editOutfit.name ?? '',
        occasion: editOutfit.occasion ?? null,
      },
    });
    setEditLoaded(true);
    setDraftPrompted(true);
  }, [editOutfit, editLoaded, isEditMode]);

  useEffect(() => {
    if (isEditMode || draftPrompted) return;
    const draft = loadDraft();
    if (draft && draft.items.length > 0) {
      setPendingDraft(draft);
    }
    setDraftPrompted(true);
  }, [draftPrompted, isEditMode]);

  const { data: draftItemsData } = useItems(
    pendingDraft
      ? { ids: pendingDraft.items.join(','), is_archived: false }
      : { is_archived: false },
    1,
    50
  );

  const handleResumeDraft = useCallback(() => {
    if (!pendingDraft || !draftItemsData?.items) return;
    const byId = new Map(draftItemsData.items.map((i) => [i.id, i]));
    const resumedItems: StudioItem[] = pendingDraft.items
      .map((id) => byId.get(id))
      .filter((item): item is NonNullable<typeof item> => item !== undefined)
      .map((item) => ({
        id: item.id,
        type: item.type,
        name: item.name ?? null,
        thumbnail_url: item.thumbnail_url ?? null,
        image_url: item.image_url ?? null,
        primary_color: item.primary_color ?? null,
      }));
    dispatch({
      type: 'LOAD',
      state: {
        items: resumedItems,
        name: pendingDraft.name,
        occasion: pendingDraft.occasion,
      },
    });
    setPendingDraft(null);
  }, [pendingDraft, draftItemsData]);

  const handleDiscardDraft = useCallback(() => {
    clearDraft();
    setPendingDraft(null);
  }, []);

  useEffect(() => {
    if (isEditMode) return;
    if (!state.isDirty) return;
    const timer = setTimeout(() => {
      saveDraft({
        items: state.items.map((i) => i.id),
        name: state.name,
        occasion: state.occasion,
      });
    }, 500);
    return () => clearTimeout(timer);
  }, [state.isDirty, state.items, state.name, state.occasion, isEditMode]);

  const selectedIds = useMemo(
    () => new Set(state.items.map((i) => i.id)),
    [state.items]
  );

  const handleToggle = useCallback((itemId: string) => {
    const existing = state.items.find((i) => i.id === itemId);
    if (existing) {
      dispatch({ type: 'REMOVE_ITEM', itemId });
      return;
    }
    const fromData = draftItemsData?.items.find((i) => i.id === itemId);
    if (!fromData) return;
    dispatch({
      type: 'ADD_ITEM',
      item: {
        id: fromData.id,
        type: fromData.type,
        name: fromData.name ?? null,
        thumbnail_url: fromData.thumbnail_url ?? null,
        image_url: fromData.image_url ?? null,
        primary_color: fromData.primary_color ?? null,
      },
    });
  }, [state.items, draftItemsData]);

  const handleSave = async (markWorn: boolean) => {
    if (state.items.length === 0) {
      toast.error('Pick at least one item');
      return;
    }
    if (!state.occasion) {
      toast.error('Pick an occasion');
      return;
    }

    if (isEditMode && editId) {
      try {
        await patchMutation.mutateAsync({
          id: editId,
          payload: {
            name: state.name.trim() || undefined,
            items: state.items.map((i) => i.id),
          },
        });
        toast.success('Outfit updated');
        router.push(`/dashboard/outfits/${editId}`);
      } catch (error) {
        if (isWornImmutableError(error)) {
          setWornConflictOpen(true);
          return;
        }
        toast.error(getErrorMessage(error, 'Failed to save outfit'));
      }
      return;
    }

    if (!markWorn && !state.name.trim()) {
      toast.error('Give your lookbook entry a name before saving');
      return;
    }

    try {
      await createMutation.mutateAsync({
        items: state.items.map((i) => i.id),
        occasion: state.occasion,
        name: state.name.trim() || undefined,
        scheduled_for: markWorn
          ? new Date().toISOString().slice(0, 10)
          : null,
        mark_worn: markWorn,
      });
      clearDraft();
      toast.success(markWorn ? 'Saved and marked worn' : 'Saved to lookbook');
      router.push(
        markWorn
          ? '/dashboard/outfits?filter=worn'
          : '/dashboard/outfits?filter=my-looks'
      );
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to save outfit'));
    }
  };

  const mutationPending = isEditMode ? patchMutation.isPending : createMutation.isPending;
  const canSave =
    state.items.length > 0 && state.occasion !== null && !mutationPending;

  const editPhase = isEditMode
    ? computeEditLoadPhase({
        isLoading: editLoading,
        isError: editIsError,
        errorStatus: editErrorStatus,
        hasData: !!editOutfit,
        isWorn: editOutfitIsWorn,
        editLoaded,
      })
    : 'ready';

  if (isEditMode && editPhase === 'loading') {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isEditMode && editPhase === 'missing') {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] px-4 text-center">
        <AlertCircle className="h-10 w-10 text-muted-foreground mb-3" />
        <h2 className="text-lg font-semibold mb-1">Outfit not found</h2>
        <p className="text-sm text-muted-foreground mb-4 max-w-md">
          This outfit no longer exists. It may have been deleted from another tab or device.
        </p>
        <Button asChild>
          <Link href="/dashboard/outfits">Back to outfits</Link>
        </Button>
      </div>
    );
  }

  if (isEditMode && editPhase === 'error') {
    const isAuthError = editErrorStatus === 401 || editErrorStatus === 403;
    const headline = isAuthError
      ? "You can't edit this outfit"
      : "Couldn't load this outfit";
    const body = isAuthError
      ? 'Your session may have expired or this outfit belongs to another account.'
      : 'Something went wrong while loading this outfit. Check your connection and try again.';
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] px-4 text-center">
        <AlertTriangle className="h-10 w-10 text-destructive mb-3" />
        <h2 className="text-lg font-semibold mb-1">{headline}</h2>
        <p className="text-sm text-muted-foreground mb-4 max-w-md">{body}</p>
        <div className="flex gap-2">
          {!isAuthError && (
            <Button variant="outline" onClick={() => refetchEdit()}>
              Try again
            </Button>
          )}
          <Button asChild>
            <Link href="/dashboard/outfits">Back to outfits</Link>
          </Button>
        </div>
      </div>
    );
  }

  if (isEditMode && editPhase === 'wornImmutable' && editOutfit && editId) {
    return (
      <>
        <div className="flex flex-col items-center justify-center h-[60vh] px-4 text-center">
          <AlertCircle className="h-10 w-10 text-muted-foreground mb-3" />
          <h2 className="text-lg font-semibold mb-1">This outfit has been worn</h2>
          <p className="text-sm text-muted-foreground mb-4 max-w-md">
            Worn outfits can&apos;t be edited because they&apos;re part of your wear history.
            You can save a copy as a new lookbook entry instead.
          </p>
          <div className="flex gap-2">
            <Button variant="outline" asChild>
              <Link href={`/dashboard/outfits/${editId}`}>Back to outfit</Link>
            </Button>
            <Button onClick={() => setCloneDialogOpen(true)}>Save as new</Button>
          </div>
        </div>
        <CloneToLookbookDialog
          open={cloneDialogOpen}
          sourceOutfitId={editId}
          sourceOccasion={editOutfit.occasion}
          onClose={() => setCloneDialogOpen(false)}
          onSuccess={(newId) => router.push(`/dashboard/outfits/${newId}`)}
        />
      </>
    );
  }

  const cancelHref = isEditMode && editId ? `/dashboard/outfits/${editId}` : '/dashboard/outfits';

  return (
    <div className="flex flex-col h-full">
      <div className="sticky top-0 z-10 bg-background border-b px-4 py-3 flex items-center justify-between">
        <Button variant="ghost" size="sm" asChild>
          <Link href={cancelHref}>
            <ChevronLeft className="h-4 w-4 mr-1" />
            Cancel
          </Link>
        </Button>
        <h1 className="text-lg font-semibold">
          {isEditMode ? 'Edit Outfit' : 'Studio'}
        </h1>
        <div className="flex flex-col items-end">
          <div className="flex gap-2">
            {!isEditMode && (
              <Button
                variant="outline"
                size="sm"
                disabled={!canSave}
                onClick={() => handleSave(true)}
              >
                {mutationPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  'Wear Today'
                )}
              </Button>
            )}
            <Button size="sm" disabled={!canSave} onClick={() => handleSave(false)}>
              {mutationPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : isEditMode ? (
                'Save Changes'
              ) : (
                'Save to Lookbook'
              )}
            </Button>
          </div>
          {!canSave && !mutationPending && (
            <p className="text-xs text-muted-foreground mt-1 text-right">
              {state.items.length === 0 && state.occasion === null
                ? 'Pick at least one item and an occasion'
                : state.items.length === 0
                  ? 'Pick at least one item'
                  : state.occasion === null
                    ? 'Pick an occasion'
                    : ''}
            </p>
          )}
        </div>
      </div>

      {pendingDraft && (
        <div className="bg-blue-50 border-b border-blue-200 px-4 py-3 flex items-center justify-between gap-4">
          <p className="text-sm text-blue-900">
            You have an unsaved draft from your last session. Resume it?
          </p>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={handleDiscardDraft}>
              Start fresh
            </Button>
            <Button size="sm" onClick={handleResumeDraft}>
              Resume
            </Button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-6xl mx-auto space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              <h2 className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                Canvas
              </h2>
              <CanvasPanel
                items={state.items}
                onRemove={(id) => dispatch({ type: 'REMOVE_ITEM', itemId: id })}
              />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                Details
              </h2>
              <DetailsPanel
                items={state.items}
                name={state.name}
                occasion={state.occasion}
                onNameChange={(n) => dispatch({ type: 'SET_NAME', name: n })}
                onOccasionChange={(o) =>
                  dispatch({ type: 'SET_OCCASION', occasion: o })
                }
                onAiMerge={(merged) =>
                  dispatch({ type: 'REPLACE_CANVAS', items: merged })
                }
              />
            </div>
          </div>

          <div>
            <h2 className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
              Your Wardrobe
            </h2>
            <ItemPicker
              selectedIds={selectedIds}
              onToggle={handleToggle}
              hideNeedsWash={true}
              emptyMessage="No items in your wardrobe yet. Add items first."
              heightClass="h-[280px]"
            />
          </div>
        </div>
      </div>

      <AlertDialog open={wornConflictOpen} onOpenChange={setWornConflictOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>This outfit has been worn</AlertDialogTitle>
            <AlertDialogDescription>
              Worn outfits can&apos;t be edited because they&apos;re part of your wear history. Save your
              changes as a new lookbook entry instead?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Discard changes</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setWornConflictOpen(false);
                setCloneDialogOpen(true);
              }}
            >
              Save as new
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {isEditMode && editId && editOutfit && (
        <CloneToLookbookDialog
          open={cloneDialogOpen}
          sourceOutfitId={editId}
          sourceOccasion={editOutfit.occasion}
          onClose={() => setCloneDialogOpen(false)}
          onSuccess={(newId) => router.push(`/dashboard/outfits/${newId}`)}
        />
      )}
    </div>
  );
}
