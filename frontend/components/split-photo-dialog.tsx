'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader2, Plus, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { getErrorMessage } from '@/lib/api';
import { useDetectGarments, useSplitItem } from '@/lib/hooks/use-split';
import {
  MAX_BOXES,
  moveBox,
  newBox,
  resizeBox,
  type Box,
  type Handle,
} from '@/lib/split-boxes';

interface SplitPhotoDialogProps {
  itemId: string;
  imageUrl: string;
  open: boolean;
  onClose: () => void;
  /** Called after the items were created, so the caller can close what showed the original. */
  onDone?: () => void;
}

interface NumberedBox extends Box {
  key: number;
}

interface Drag {
  key: number;
  mode: 'move' | Handle;
  startX: number;
  startY: number;
  start: Box;
}

const HANDLES: { handle: Handle; className: string }[] = [
  { handle: 'nw', className: '-left-2 -top-2 cursor-nwse-resize' },
  { handle: 'ne', className: '-right-2 -top-2 cursor-nesw-resize' },
  { handle: 'sw', className: '-bottom-2 -left-2 cursor-nesw-resize' },
  { handle: 'se', className: '-bottom-2 -right-2 cursor-nwse-resize' },
];

export function SplitPhotoDialog({ itemId, imageUrl, open, onClose, onDone }: SplitPhotoDialogProps) {
  const t = useTranslations('wardrobe.splitPhoto');
  const tc = useTranslations('common');
  const detect = useDetectGarments();
  const split = useSplitItem();
  const [boxes, setBoxes] = useState<NumberedBox[]>([]);
  const nextKey = useRef(1);
  const frame = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const started = useRef(false);

  const runDetection = () => {
    detect.mutate(itemId, {
      onSuccess: ({ garments }) =>
        setBoxes(
          garments.slice(0, MAX_BOXES).map((g) => ({
            key: nextKey.current++,
            left: g.left,
            top: g.top,
            width: g.width,
            height: g.height,
          })),
        ),
    });
  };

  useEffect(() => {
    if (!open || started.current) return;
    started.current = true;
    runDetection();
    // runDetection only needs to run once per opening
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const begin = (event: React.PointerEvent, box: NumberedBox, mode: Drag['mode']) => {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = {
      key: box.key,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      start: { left: box.left, top: box.top, width: box.width, height: box.height },
    };
  };

  const update = (event: React.PointerEvent) => {
    const active = drag.current;
    const rect = frame.current?.getBoundingClientRect();
    if (!active || !rect || rect.width === 0 || rect.height === 0) return;
    const dx = (event.clientX - active.startX) / rect.width;
    const dy = (event.clientY - active.startY) / rect.height;
    const next =
      active.mode === 'move'
        ? moveBox(active.start, dx, dy)
        : resizeBox(active.start, active.mode, dx, dy);
    setBoxes((all) => all.map((b) => (b.key === active.key ? { ...b, ...next } : b)));
  };

  const end = () => {
    drag.current = null;
  };

  const handleCreate = async () => {
    try {
      const result = await split.mutateAsync({ itemId, boxes });
      toast.success(t('created', { count: result.item_ids.length }));
      onClose();
      onDone?.();
    } catch (error) {
      toast.error(getErrorMessage(error, t('createFailed')));
    }
  };

  const detecting = detect.isPending;
  const detectFailed = detect.isError;
  const noneFound = detect.isSuccess && boxes.length === 0 && detect.data.garments.length === 0;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="flex justify-center bg-muted rounded-md p-2">
          <div ref={frame} className="relative inline-block max-w-full touch-none select-none">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={imageUrl}
              alt={t('photoAlt')}
              draggable={false}
              className="block max-h-[50vh] w-auto max-w-full"
            />
            {boxes.map((box, index) => (
              <div
                key={box.key}
                role="group"
                aria-label={t('boxLabel', { number: index + 1 })}
                data-testid={`split-box-${index + 1}`}
                className="absolute cursor-move border-2 border-primary bg-primary/10"
                style={{
                  left: `${box.left * 100}%`,
                  top: `${box.top * 100}%`,
                  width: `${box.width * 100}%`,
                  height: `${box.height * 100}%`,
                  touchAction: 'none',
                }}
                onPointerDown={(e) => begin(e, box, 'move')}
                onPointerMove={update}
                onPointerUp={end}
                onPointerCancel={end}
              >
                <span className="absolute left-0 top-0 rounded-br bg-primary px-1.5 text-xs font-semibold text-primary-foreground">
                  {index + 1}
                </span>
                {HANDLES.map(({ handle, className }) => (
                  <span
                    key={handle}
                    aria-hidden="true"
                    data-handle={handle}
                    className={`absolute h-4 w-4 rounded-full border-2 border-primary bg-background ${className}`}
                    style={{ touchAction: 'none' }}
                    onPointerDown={(e) => begin(e, box, handle)}
                    onPointerMove={update}
                    onPointerUp={end}
                    onPointerCancel={end}
                  />
                ))}
              </div>
            ))}
            {detecting && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/70 text-sm">
                <Loader2 className="h-5 w-5 animate-spin" />
                {t('detecting')}
              </div>
            )}
          </div>
        </div>

        {detectFailed && (
          <div className="flex items-center justify-between gap-2 text-sm text-destructive">
            <span>{t('detectFailed')}</span>
            <Button variant="outline" size="sm" onClick={runDetection}>
              {t('retry')}
            </Button>
          </div>
        )}
        {noneFound && <p className="text-sm text-muted-foreground">{t('noneFound')}</p>}
        {!detecting && !detectFailed && !noneFound && (
          <p className="text-xs text-muted-foreground">{t('hint')}</p>
        )}

        {boxes.length > 0 && (
          <ul className="space-y-1">
            {boxes.map((box, index) => (
              <li key={box.key} className="flex items-center justify-between text-sm">
                <span>{t('boxLabel', { number: index + 1 })}</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  aria-label={t('removeBox', { number: index + 1 })}
                  onClick={() => setBoxes((all) => all.filter((b) => b.key !== box.key))}
                >
                  <X className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={detecting || boxes.length >= MAX_BOXES}
            onClick={() => setBoxes((all) => [...all, { key: nextKey.current++, ...newBox(all.length) }])}
          >
            <Plus className="mr-1 h-4 w-4" />
            {t('addBox')}
          </Button>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={onClose}>
              {tc('cancel')}
            </Button>
            <Button disabled={detecting || split.isPending || boxes.length === 0} onClick={handleCreate}>
              {split.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('create', { count: boxes.length })}
            </Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">{t('archiveNote')}</p>
      </DialogContent>
    </Dialog>
  );
}
