'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Pipette, X, Check, Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { CLOTHING_COLORS } from '@/lib/types';
import { useClothingColors } from '@/lib/hooks/use-translated-constants';
import { useTranslations } from 'next-intl';

interface ColorEyedropperProps {
  imageUrl: string;
  onColorSelect: (color: string) => void;
  trigger?: React.ReactNode;
}

function rgbToHex(r: number, g: number, b: number): string {
  return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('');
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  return {
    r: parseInt(hex.slice(1, 3), 16),
    g: parseInt(hex.slice(3, 5), 16),
    b: parseInt(hex.slice(5, 7), 16),
  };
}

function rgbToHsl(r: number, g: number, b: number): { h: number; s: number; l: number } {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  return { h: h * 360, s, l };
}

function colorDistance(hex1: string, hex2: string): number {
  const rgb1 = hexToRgb(hex1);
  const rgb2 = hexToRgb(hex2);
  const hsl1 = rgbToHsl(rgb1.r, rgb1.g, rgb1.b);
  const hsl2 = rgbToHsl(rgb2.r, rgb2.g, rgb2.b);

  const saturationPenalty = Math.abs(hsl1.s - hsl2.s) * 100;
  let hueDiff = Math.abs(hsl1.h - hsl2.h);
  if (hueDiff > 180) hueDiff = 360 - hueDiff;

  const hueWeight = Math.min(hsl1.s, hsl2.s) * 2;
  const hueDistance = hueDiff * hueWeight;
  const rgbDistance = Math.sqrt(
    (rgb1.r - rgb2.r) ** 2 +
    (rgb1.g - rgb2.g) ** 2 +
    (rgb1.b - rgb2.b) ** 2
  );

  return rgbDistance + saturationPenalty + hueDistance;
}

type ClothingColor = (typeof CLOTHING_COLORS)[number];

function findClosestColor(hex: string): ClothingColor {
  let closestIndex = 0;
  let minDistance = Infinity;

  for (let i = 0; i < CLOTHING_COLORS.length; i++) {
    const distance = colorDistance(hex, CLOTHING_COLORS[i].hex);
    if (distance < minDistance) {
      minDistance = distance;
      closestIndex = i;
    }
  }

  return CLOTHING_COLORS[closestIndex];
}

export function ColorEyedropper({ imageUrl, onColorSelect, trigger }: ColorEyedropperProps) {
  const t = useTranslations('dialogs.colorEyedropper');
  const clothingColors = useClothingColors();
  const [open, setOpen] = useState(false);
  const [pickedColor, setPickedColor] = useState<string | null>(null);
  const [matchedColor, setMatchedColor] = useState<ClothingColor | null>(null);
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);
  const [hoverColor, setHoverColor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [imageLoaded, setImageLoaded] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const blobUrlRef = useRef<string | null>(null);

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
      }
    };
  }, []);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setIsLoading(true);
      setError(null);
      setImageLoaded(false);
      setPickedColor(null);
      setMatchedColor(null);
    }
  }, [open]);

  // Load image onto canvas when dialog opens and canvas is ready
  useEffect(() => {
    if (!open || imageLoaded) return;

    // Small delay to ensure canvas is mounted
    const timer = setTimeout(() => {
      const canvas = canvasRef.current;
      if (!canvas) {
        setError('Canvas not available');
        setIsLoading(false);
        return;
      }

      const ctx = canvas.getContext('2d');
      if (!ctx) {
        setError('Could not get canvas context');
        setIsLoading(false);
        return;
      }

      // Fetch image as blob to avoid CORS issues with canvas
      fetch(imageUrl, { credentials: 'include' })
        .then(response => {
          if (!response.ok) throw new Error(`Failed to load image: ${response.status}`);
          return response.blob();
        })
        .then(blob => {
          // Cleanup previous blob URL
          if (blobUrlRef.current) {
            URL.revokeObjectURL(blobUrlRef.current);
          }
          const blobUrl = URL.createObjectURL(blob);
          blobUrlRef.current = blobUrl;

          const img = new Image();
          img.onload = () => {
            imageRef.current = img;

            // Scale image to fit canvas while maintaining aspect ratio
            const maxWidth = 500;
            const maxHeight = 500;
            let width = img.width;
            let height = img.height;

            if (width > maxWidth) {
              height = (height * maxWidth) / width;
              width = maxWidth;
            }
            if (height > maxHeight) {
              width = (width * maxHeight) / height;
              height = maxHeight;
            }

            canvas.width = width;
            canvas.height = height;
            ctx.drawImage(img, 0, 0, width, height);
            setIsLoading(false);
            setImageLoaded(true);
          };
          img.onerror = () => {
            setError('Failed to load image from blob');
            setIsLoading(false);
          };
          img.src = blobUrl;
        })
        .catch(err => {
          setError(err.message || 'Failed to load image');
          setIsLoading(false);
        });
    }, 100); // Small delay to ensure DOM is ready

    return () => clearTimeout(timer);
  }, [open, imageUrl, imageLoaded]);

  const getColorAtPosition = useCallback((x: number, y: number): string | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    try {
      const pixel = ctx.getImageData(x, y, 1, 1).data;
      return rgbToHex(pixel[0], pixel[1], pixel[2]);
    } catch {
      return null;
    }
  }, []);

  const handleCanvasMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = Math.floor((e.clientX - rect.left) * (canvas.width / rect.width));
    const y = Math.floor((e.clientY - rect.top) * (canvas.height / rect.height));

    setCursorPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    const color = getColorAtPosition(x, y);
    setHoverColor(color);
  }, [getColorAtPosition]);

  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = Math.floor((e.clientX - rect.left) * (canvas.width / rect.width));
    const y = Math.floor((e.clientY - rect.top) * (canvas.height / rect.height));

    const color = getColorAtPosition(x, y);
    if (color) {
      setPickedColor(color);
      setMatchedColor(findClosestColor(color));
    }
  }, [getColorAtPosition]);

  const handleConfirm = () => {
    if (matchedColor) {
      onColorSelect(matchedColor.value);
      setOpen(false);
      setPickedColor(null);
      setMatchedColor(null);
    }
  };

  const handleCanvasLeave = () => {
    setCursorPos(null);
    setHoverColor(null);
  };

  return (
    <>
      {trigger ? (
        <div onClick={() => setOpen(true)}>{trigger}</div>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={() => setOpen(true)}
          title={t('buttonTitle')}
        >
          <Pipette className="h-4 w-4" />
        </Button>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Pipette className="h-5 w-5" />
              {t('title')}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {t('description')}
            </p>

            <div className="relative flex justify-center bg-muted rounded-lg p-2 min-h-[200px]">
              {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              )}

              {error && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-destructive">
                  <AlertCircle className="h-8 w-8" />
                  <span className="text-sm">{error}</span>
                </div>
              )}

              <canvas
                ref={canvasRef}
                className={`cursor-crosshair rounded max-w-full ${isLoading || error ? 'invisible' : ''}`}
                onMouseMove={handleCanvasMove}
                onMouseLeave={handleCanvasLeave}
                onClick={handleCanvasClick}
              />

              {/* Hover preview */}
              {!isLoading && !error && cursorPos && hoverColor && (
                <div
                  className="absolute pointer-events-none z-10 flex items-center gap-2 bg-background/90 backdrop-blur-sm rounded-lg px-2 py-1 shadow-lg border"
                  style={{
                    left: Math.min(cursorPos.x + 20, 400),
                    top: Math.max(cursorPos.y - 30, 10),
                  }}
                >
                  <div
                    className="w-6 h-6 rounded border shadow-inner"
                    style={{ backgroundColor: hoverColor }}
                  />
                  <span className="text-xs font-mono">{hoverColor}</span>
                </div>
              )}
            </div>

            {/* Selected color display */}
            {pickedColor && matchedColor && (
              <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="flex flex-col items-center gap-1">
                    <div
                      className="w-10 h-10 rounded border shadow-inner"
                      style={{ backgroundColor: pickedColor }}
                    />
                    <span className="text-xs text-muted-foreground">{t('picked')}</span>
                  </div>
                  <div className="text-muted-foreground">&rarr;</div>
                  <div className="flex flex-col items-center gap-1">
                    <div
                      className="w-10 h-10 rounded border shadow-inner"
                      style={{ backgroundColor: matchedColor.hex }}
                    />
                    <span className="text-xs font-medium">{clothingColors.find((c) => c.value === matchedColor.value)?.name ?? matchedColor.name}</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setPickedColor(null);
                      setMatchedColor(null);
                    }}
                  >
                    <X className="h-4 w-4 mr-1" />
                    {t('clear')}
                  </Button>
                  <Button size="sm" onClick={handleConfirm}>
                    <Check className="h-4 w-4 mr-1" />
                    {t('useColor', { color: clothingColors.find((c) => c.value === matchedColor.value)?.name ?? matchedColor.name })}
                  </Button>
                </div>
              </div>
            )}

            {!pickedColor && (
              <div className="text-center text-sm text-muted-foreground py-2">
                {t('noColorSelected')}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
