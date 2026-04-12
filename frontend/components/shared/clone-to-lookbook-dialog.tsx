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

  const handleConfirm = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      toast.error('Please enter a name');
      return;
    }
    try {
      const result = await clone.mutateAsync({ name: trimmed });
      toast.success('Saved to lookbook');
      onSuccess?.(result.id);
      onClose();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to save to lookbook'));
    }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Save to lookbook</DialogTitle>
          <DialogDescription>
            Give this look a name so you can find it later and wear it again.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-2">
          <Label htmlFor="lookbook-name">Name</Label>
          <Input
            id="lookbook-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            placeholder="Friday brunch"
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={clone.isPending}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={clone.isPending || !name.trim()}
          >
            {clone.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
