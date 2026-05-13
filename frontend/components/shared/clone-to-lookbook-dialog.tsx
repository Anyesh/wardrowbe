'use client';

import { useState } from 'react';
import { format } from 'date-fns';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCloneToLookbook } from '@/lib/hooks/use-studio';
import { getErrorMessage } from '@/lib/api';
import { useTranslations } from 'next-intl';

interface CloneToLookbookDialogProps {
  open: boolean;
  sourceOutfitId: string;
  sourceOccasion: string;
  onClose: () => void;
  onSuccess?: (newOutfitId: string) => void;
}

function defaultCloneName(occasion: string): string {
  const occasionTitle = occasion.charAt(0).toUpperCase() + occasion.slice(1);
  return `${occasionTitle} — ${format(new Date(), 'MMM d')}`;
}

export function CloneToLookbookDialog({
  open,
  sourceOutfitId,
  sourceOccasion,
  onClose,
  onSuccess,
}: CloneToLookbookDialogProps) {
  const [name, setName] = useState(() => defaultCloneName(sourceOccasion));
  const clone = useCloneToLookbook(sourceOutfitId);
  const t = useTranslations('dialogs.cloneToLookbook');

  const handleConfirm = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      toast.error(t('errorEmpty'));
      return;
    }
    try {
      const result = await clone.mutateAsync({ name: trimmed });
      toast.success(t('saved'));
      onSuccess?.(result.id);
      onClose();
    } catch (error) {
      toast.error(getErrorMessage(error, t('saveError')));
    }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>
            {t('description')}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-2">
          <Label htmlFor="lookbook-name">{t('name')}</Label>
          <Input
            id="lookbook-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            placeholder={t('namePlaceholder')}
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={clone.isPending}>
            {t('cancel')}
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={clone.isPending || !name.trim()}
          >
            {clone.isPending ? t('saving') : t('save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
