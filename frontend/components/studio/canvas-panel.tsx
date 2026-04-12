'use client';

import Image from 'next/image';
import { X } from 'lucide-react';

import { ITEM_ROLE } from '@/lib/studio/canonical-order';
import { cn } from '@/lib/utils';
import type { StudioItem } from '@/lib/studio/editor-state';

interface CanvasPanelProps {
  items: StudioItem[];
  onRemove: (itemId: string) => void;
}

function roleLabel(type: string): string {
  const role = ITEM_ROLE[type];
  if (!role) return type;
  return role.replace('_', ' ');
}

export function CanvasPanel({ items, onRemove }: CanvasPanelProps) {
  if (items.length === 0) {
    return (
      <div className="min-h-[240px] rounded-lg border-2 border-dashed border-muted-foreground/30 bg-muted/20 flex items-center justify-center p-6">
        <p className="text-sm text-muted-foreground text-center">
          Tap items below to start building your outfit
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-muted/10 p-4">
      <div className="flex flex-wrap gap-3">
        {items.map((item) => (
          <div key={item.id} className="relative w-24 shrink-0">
            <button
              type="button"
              onClick={() => onRemove(item.id)}
              className={cn(
                'absolute -top-2 -right-2 z-10 rounded-full bg-destructive text-destructive-foreground',
                'p-1 shadow-md hover:bg-destructive/90 focus:outline-none focus:ring-2 focus:ring-destructive/50'
              )}
              aria-label={`Remove ${item.name || item.type}`}
            >
              <X className="h-3 w-3" />
            </button>
            <div className="aspect-square rounded-lg overflow-hidden border-2 border-primary/50 bg-background">
              {item.thumbnail_url || item.image_url ? (
                <Image
                  src={(item.thumbnail_url || item.image_url)!}
                  alt={item.name || item.type}
                  width={96}
                  height={96}
                  className="object-cover w-full h-full"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <span className="text-xs text-muted-foreground">
                    {item.type}
                  </span>
                </div>
              )}
            </div>
            <p className="text-[10px] text-center text-muted-foreground mt-1 truncate capitalize">
              {roleLabel(item.type)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
