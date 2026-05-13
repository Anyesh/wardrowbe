'use client';

import { useState } from 'react';
import { Loader2, Sparkles, Check, AlertCircle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { toast } from 'sonner';
import { useGeneratePairings } from '@/lib/hooks/use-pairings';
import { Item, Pairing } from '@/lib/types';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

interface GeneratePairingsDialogProps {
  item: Item | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// Images now use signed URLs from backend (item.image_url, item.thumbnail_url)

export function GeneratePairingsDialog({
  item,
  open,
  onOpenChange,
}: GeneratePairingsDialogProps) {
  const [numPairings, setNumPairings] = useState(3);
  const [generatedPairings, setGeneratedPairings] = useState<Pairing[] | null>(null);
  const generatePairings = useGeneratePairings();
  const router = useRouter();
  const t = useTranslations('dialogs.generatePairings');

  const handleGenerate = async () => {
    if (!item) return;

    try {
      const result = await generatePairings.mutateAsync({
        itemId: item.id,
        numPairings,
      });
      setGeneratedPairings(result.pairings);
      toast.success(t('success', { count: result.generated }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to generate pairings';
      toast.error(message);
    }
  };

  const handleViewPairings = () => {
    onOpenChange(false);
    setGeneratedPairings(null);
    router.push('/dashboard/pairings');
  };

  const handleClose = () => {
    onOpenChange(false);
    setGeneratedPairings(null);
  };

  if (!item) return null;

  const imageUrl = item.thumbnail_url || item.image_url || item.image_path;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>
            {t('description')}
          </DialogDescription>
        </DialogHeader>

        {!generatedPairings ? (
          // Generation form
          <div className="space-y-6 py-4 min-w-0">
            {/* Source item preview */}
            <div className="flex items-center gap-4 p-3 rounded-lg bg-muted/50 border">
              <div className="w-16 h-16 rounded-lg bg-muted overflow-hidden relative border-2 border-primary/30">
                <Image
                  src={imageUrl}
                  alt={item.name || item.type}
                  fill
                  className="object-cover"
                  sizes="64px"
                />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{item.name || item.type}</p>
                {item.primary_color && (
                  <p className="text-sm text-muted-foreground capitalize">
                    {item.primary_color} {item.type}
                  </p>
                )}
              </div>
            </div>

            {/* Number of pairings selector */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label>{t('numOutfits')}</Label>
                <span className="text-sm font-medium text-primary">{numPairings}</span>
              </div>
              <Slider
                value={[numPairings]}
                onValueChange={([value]) => setNumPairings(value)}
                min={1}
                max={5}
                step={1}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                {t('numOutfitsDesc')}
              </p>
            </div>
          </div>
        ) : (
          // Success state
          <div className="py-6 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 mx-auto flex items-center justify-center">
              <Check className="h-8 w-8 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="font-medium text-lg">
                {t('success', { count: generatedPairings.length })}
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                {t('successDesc')}
              </p>
            </div>

            {/* Preview of generated pairings */}
            <div className="flex justify-center gap-2 flex-wrap">
              {generatedPairings.slice(0, 3).map((pairing) => (
                <div
                  key={pairing.id}
                  className="flex gap-1 p-1 rounded-lg bg-muted border"
                >
                  {pairing.items.slice(0, 3).map((pairingItem) => (
                    <div
                      key={pairingItem.id}
                      className="w-8 h-8 rounded overflow-hidden relative"
                    >
                      {pairingItem.thumbnail_url ? (
                        <Image
                          src={pairingItem.thumbnail_url}
                          alt={pairingItem.type}
                          fill
                          className="object-cover"
                          sizes="32px"
                        />
                      ) : (
                        <div className="w-full h-full bg-muted-foreground/20" />
                      )}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}

        <DialogFooter>
          {!generatedPairings ? (
            <>
              <Button variant="outline" onClick={handleClose}>
                {t('cancel')}
              </Button>
              <Button
                onClick={handleGenerate}
                disabled={generatePairings.isPending}
              >
                {generatePairings.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    {t('generating')}
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" />
                    {t('generate')}
                  </>
                )}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={handleClose}>
                {t('close')}
              </Button>
              <Button onClick={handleViewPairings}>
                {t('viewPairings')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
