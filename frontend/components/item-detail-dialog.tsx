'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import {
  Heart,
  Pencil,
  Trash2,
  X,
  Loader2,
  Calendar,
  Tag,
  Palette,
  Shirt,
  Sparkles,
  RefreshCw,
  RotateCcw,
  RotateCw,
  Eraser,
  Layers,
  Droplets,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Plus,
  Star,
  ImageIcon,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { toast } from 'sonner';
import { useUpdateItem, useDeleteItem, useReanalyzeItem, useRotateImage, useRemoveBackground, useLogWash, useWashHistory, useItemWearStats, useItemWearHistory, useAddItemImage, useDeleteItemImage, useSetPrimaryImage } from '@/lib/hooks/use-items';
import { Item, CLOTHING_TYPES, CLOTHING_COLORS } from '@/lib/types';
import { ColorEyedropper } from '@/components/color-eyedropper';
import { GeneratePairingsDialog } from '@/components/generate-pairings-dialog';
import { useFeatures } from '@/lib/hooks/use-features';

interface ItemDetailDialogProps {
  item: Item | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// Images now use signed URLs from backend (item.image_url, item.thumbnail_url)

export function ItemDetailDialog({ item, open, onOpenChange }: ItemDetailDialogProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showPairingsDialog, setShowPairingsDialog] = useState(false);
  const [imageKey, setImageKey] = useState(0);
  const [editForm, setEditForm] = useState({
    name: '',
    type: '',
    subtype: '',
    brand: '',
    primary_color: '',
    notes: '',
    favorite: false,
    wash_interval: undefined as number | undefined,
  });
  const [showWashHistory, setShowWashHistory] = useState(false);
  const [showWearHistory, setShowWearHistory] = useState(false);
  const [activeImageIndex, setActiveImageIndex] = useState(0);

  const updateItem = useUpdateItem();
  const deleteItem = useDeleteItem();
  const reanalyzeItem = useReanalyzeItem();
  const rotateImage = useRotateImage();
  const removeBackground = useRemoveBackground();
  const { data: features } = useFeatures();
  const logWash = useLogWash();
  const { data: washHistory } = useWashHistory(item?.id || '');
  const { data: wearStats } = useItemWearStats(item?.id || '');
  const { data: wearHistory } = useItemWearHistory(item?.id || '', 20);
  const addImage = useAddItemImage();
  const deleteImage = useDeleteItemImage();
  const setPrimary = useSetPrimaryImage();

  useEffect(() => {
    if (item) {
      setEditForm({
        name: item.name || '',
        type: item.type,
        subtype: item.subtype || '',
        brand: item.brand || '',
        primary_color: item.primary_color || '',
        notes: item.notes || '',
        favorite: item.favorite,
        wash_interval: item.wash_interval ?? undefined,
      });
      setIsEditing(false);
      setActiveImageIndex(0);
    }
  }, [item?.id]);

  if (!item) return null;

  const handleSave = async () => {
    try {
      await updateItem.mutateAsync({
        id: item.id,
        data: {
          name: editForm.name || undefined,
          type: editForm.type,
          subtype: editForm.subtype || undefined,
          brand: editForm.brand || undefined,
          primary_color: editForm.primary_color || undefined,
          notes: editForm.notes || undefined,
          favorite: editForm.favorite,
          wash_interval: editForm.wash_interval,
        },
      });
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to update item:', error);
    }
  };

  const handleMarkWashed = async () => {
    try {
      await logWash.mutateAsync({ id: item.id });
      toast.success('Marked as washed');
    } catch (error) {
      console.error('Failed to log wash:', error);
      toast.error('Failed to mark as washed');
    }
  };

  const handleDelete = async () => {
    try {
      await deleteItem.mutateAsync(item.id);
      setShowDeleteConfirm(false);
      onOpenChange(false);
      toast.success('Item deleted', {
        description: item.name ? `"${item.name}" has been removed.` : 'Item removed from your wardrobe.',
      });
    } catch (error) {
      console.error('Failed to delete item:', error);
      toast.error('Failed to delete', {
        description: 'Something went wrong. Please try again.',
      });
    }
  };

  const handleToggleFavorite = async () => {
    try {
      await updateItem.mutateAsync({
        id: item.id,
        data: { favorite: !item.favorite },
      });
    } catch (error) {
      console.error('Failed to toggle favorite:', error);
    }
  };

  const handleReanalyze = async () => {
    try {
      await reanalyzeItem.mutateAsync(item.id);
      // Status will update to 'processing' and UI will reflect it
    } catch (error) {
      console.error('Failed to trigger re-analysis:', error);
    }
  };

  const handleRotate = async (direction: 'cw' | 'ccw') => {
    try {
      await rotateImage.mutateAsync({ id: item.id, direction });
      setImageKey((k) => k + 1);
      toast.success('Image rotated');
    } catch (error) {
      console.error('Failed to rotate image:', error);
      toast.error('Failed to rotate image');
    }
  };

  const handleRemoveBackground = async () => {
    try {
      await removeBackground.mutateAsync({ id: item.id });
      setImageKey((k) => k + 1);
      toast.success('Background removed');
    } catch (error) {
      console.error('Failed to remove background:', error);
      toast.error('Failed to remove background');
    }
  };

  const isAnalyzing = reanalyzeItem.isPending || item.status === 'processing';

  // Use signed URL from backend for better quality in detail view
  const imageUrl = item.image_url || item.image_path;
  const colorInfo = CLOTHING_COLORS.find((c) => c.value === item.primary_color);
  const typeInfo = CLOTHING_TYPES.find((t) => t.value === item.type);

  // AI-generated tags
  const tags = item.tags || {};
  const hasAiTags = !!(tags.colors?.length || tags.pattern || tags.material ||
                   tags.style?.length || tags.season?.length || tags.formality || tags.fit ||
                   tags.occasion?.length || tags.condition || tags.features?.length);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] flex flex-col p-0 overflow-hidden [&>button]:hidden">
          {/* Header - sticky */}
          <DialogHeader className="flex flex-row items-center justify-between space-y-0 p-4 border-b flex-shrink-0">
            <DialogTitle className="text-xl min-w-0 truncate">
              {item.name || typeInfo?.label || item.type}
            </DialogTitle>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={handleToggleFavorite}
                disabled={updateItem.isPending}
                title="Toggle favorite"
              >
                <Heart
                  className={`h-5 w-5 ${
                    item.favorite ? 'fill-red-500 text-red-500' : 'text-muted-foreground'
                  }`}
                />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowPairingsDialog(true)}
                disabled={item.status !== 'ready'}
                title="Find matching outfits"
              >
                <Layers className="h-5 w-5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleReanalyze}
                disabled={isAnalyzing}
                title={isAnalyzing ? 'Analysis in progress...' : 'Re-analyze with AI'}
              >
                <RefreshCw
                  className={`h-5 w-5 ${isAnalyzing ? 'animate-spin text-primary' : ''}`}
                />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => handleRotate('ccw')}
                disabled={rotateImage.isPending}
                title="Rotate left"
              >
                {rotateImage.isPending ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <RotateCcw className="h-5 w-5" />
                )}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => handleRotate('cw')}
                disabled={rotateImage.isPending}
                title="Rotate right"
              >
                {rotateImage.isPending ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <RotateCw className="h-5 w-5" />
                )}
              </Button>
              {features?.background_removal && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleRemoveBackground}
                  disabled={removeBackground.isPending || !item.image_url}
                  title="Remove background"
                >
                  {removeBackground.isPending ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <Eraser className="h-5 w-5" />
                  )}
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsEditing(!isEditing)}
                title={isEditing ? 'Cancel editing' : 'Edit item'}
              >
                {isEditing ? (
                  <X className="h-5 w-5" />
                ) : (
                  <Pencil className="h-5 w-5" />
                )}
              </Button>
              <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)} className="rounded-full" title="Close">
                <X className="h-5 w-5" />
              </Button>
            </div>
          </DialogHeader>

          {/* Scrollable content */}
          <div className="flex-1 overflow-y-auto overscroll-contain p-6 pt-4">
            <div className="grid gap-6 sm:grid-cols-2 [&>*]:min-w-0">
            {/* Image Gallery */}
            <div className="space-y-2">
              <div className="relative aspect-square bg-muted rounded-lg overflow-hidden">
                {(() => {
                  const allImages = [
                    { url: `${imageUrl}&v=${imageKey}`, id: 'primary' },
                    ...(item.additional_images || []).map((img) => ({ url: img.image_url, id: img.id })),
                  ];
                  const currentImage = allImages[activeImageIndex] || allImages[0];
                  return (
                    <>
                      <Image
                        key={`${currentImage.id}-${imageKey}`}
                        src={currentImage.url}
                        alt={item.name || item.type}
                        fill
                        className="object-cover"
                        sizes="(max-width: 640px) 100vw, 50vw"
                      />
                      {allImages.length > 1 && (
                        <>
                          <button
                            className="absolute left-1 top-1/2 -translate-y-1/2 bg-black/50 text-white rounded-full p-1 hover:bg-black/70"
                            onClick={() => setActiveImageIndex((i) => (i - 1 + allImages.length) % allImages.length)}
                          >
                            <ChevronLeft className="h-4 w-4" />
                          </button>
                          <button
                            className="absolute right-1 top-1/2 -translate-y-1/2 bg-black/50 text-white rounded-full p-1 hover:bg-black/70"
                            onClick={() => setActiveImageIndex((i) => (i + 1) % allImages.length)}
                          >
                            <ChevronRight className="h-4 w-4" />
                          </button>
                          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
                            {allImages.map((_, idx) => (
                              <button
                                key={idx}
                                className={`w-1.5 h-1.5 rounded-full ${idx === activeImageIndex ? 'bg-white' : 'bg-white/50'}`}
                                onClick={() => setActiveImageIndex(idx)}
                              />
                            ))}
                          </div>
                        </>
                      )}
                    </>
                  );
                })()}
                {isAnalyzing && (
                  <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-2">
                    <Loader2 className="h-8 w-8 text-white animate-spin" />
                    <span className="text-white text-sm font-medium">AI Analyzing...</span>
                  </div>
                )}
              </div>
              {/* Thumbnail strip */}
              {(item.additional_images?.length > 0 || isEditing) && (
                <div className="flex gap-1.5 overflow-x-auto">
                  <button
                    className={`relative w-12 h-12 rounded border-2 overflow-hidden flex-shrink-0 ${activeImageIndex === 0 ? 'border-primary' : 'border-transparent'}`}
                    onClick={() => setActiveImageIndex(0)}
                  >
                    <Image src={imageUrl} alt="Primary" fill className="object-cover" sizes="48px" />
                  </button>
                  {(item.additional_images || []).map((img, idx) => (
                    <div key={img.id} className="relative flex-shrink-0">
                      <button
                        className={`relative w-12 h-12 rounded border-2 overflow-hidden ${activeImageIndex === idx + 1 ? 'border-primary' : 'border-transparent'}`}
                        onClick={() => setActiveImageIndex(idx + 1)}
                      >
                        <Image src={img.thumbnail_url || img.image_url} alt="" fill className="object-cover" sizes="48px" />
                      </button>
                      {isEditing && (
                        <div className="absolute -top-1 -right-1 flex gap-0.5">
                          <button
                            className="bg-primary text-primary-foreground rounded-full p-0.5 hover:bg-primary/90"
                            title="Set as primary"
                            onClick={() => {
                              setPrimary.mutate({ itemId: item.id, imageId: img.id });
                              setActiveImageIndex(0);
                            }}
                          >
                            <Star className="h-2.5 w-2.5" />
                          </button>
                          <button
                            className="bg-destructive text-destructive-foreground rounded-full p-0.5 hover:bg-destructive/90"
                            title="Delete image"
                            onClick={() => {
                              deleteImage.mutate({ itemId: item.id, imageId: img.id });
                              if (activeImageIndex > idx) setActiveImageIndex((i) => i - 1);
                            }}
                          >
                            <X className="h-2.5 w-2.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                  {isEditing && (item.additional_images?.length || 0) < 4 && (
                    <label
                      className="w-12 h-12 rounded border-2 border-dashed border-muted-foreground/30 flex items-center justify-center cursor-pointer hover:border-primary/50 flex-shrink-0"
                    >
                      {addImage.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                      ) : (
                        <Plus className="h-4 w-4 text-muted-foreground" />
                      )}
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            addImage.mutate({ itemId: item.id, file });
                          }
                          e.target.value = '';
                        }}
                      />
                    </label>
                  )}
                </div>
              )}
            </div>

            {/* Details */}
            <div className="space-y-4">
              {isEditing ? (
                // Edit form
                <div className="space-y-3">
                  <div className="space-y-2">
                    <Label>Name</Label>
                    <Input
                      value={editForm.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      placeholder="Item name"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Type</Label>
                    <Select
                      value={editForm.type}
                      onValueChange={(v) => setEditForm({ ...editForm, type: v })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {CLOTHING_TYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>
                            {t.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Brand</Label>
                    <Input
                      value={editForm.brand}
                      onChange={(e) => setEditForm({ ...editForm, brand: e.target.value })}
                      placeholder="Brand name"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Primary Color</Label>
                    <div className="flex gap-2">
                      <Select
                        value={editForm.primary_color}
                        onValueChange={(v) => setEditForm({ ...editForm, primary_color: v })}
                      >
                        <SelectTrigger className="flex-1">
                          <SelectValue placeholder="Select color" />
                        </SelectTrigger>
                        <SelectContent>
                          {CLOTHING_COLORS.map((c) => (
                            <SelectItem key={c.value} value={c.value}>
                              <div className="flex items-center gap-2">
                                <div
                                  className="w-3 h-3 rounded-full border"
                                  style={{ backgroundColor: c.hex }}
                                />
                                {c.name}
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <ColorEyedropper
                        imageUrl={imageUrl}
                        onColorSelect={(color) => setEditForm({ ...editForm, primary_color: color })}
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>Notes</Label>
                    <Textarea
                      value={editForm.notes}
                      onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                      placeholder="Additional notes..."
                      rows={3}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Wash Interval (wears)</Label>
                    <Input
                      type="number"
                      min={1}
                      max={100}
                      value={editForm.wash_interval ?? ''}
                      onChange={(e) => setEditForm({ ...editForm, wash_interval: e.target.value ? parseInt(e.target.value) : undefined })}
                      placeholder={`Default: ${item.effective_wash_interval}`}
                    />
                    <p className="text-xs text-muted-foreground">
                      Number of wears before this item needs washing. Leave blank for default.
                    </p>
                  </div>
                  <div className="flex gap-2 pt-2">
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={() => setIsEditing(false)}
                    >
                      Cancel
                    </Button>
                    <Button
                      className="flex-1"
                      onClick={handleSave}
                      disabled={updateItem.isPending}
                    >
                      {updateItem.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : null}
                      Save
                    </Button>
                  </div>
                </div>
              ) : (
                // View mode
                <div className="space-y-4">
                  {/* Basic info */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <Shirt className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{typeInfo?.label || item.type}</span>
                      {item.subtype && (
                        <span className="text-muted-foreground">• {item.subtype}</span>
                      )}
                    </div>
                    {item.brand && (
                      <div className="flex items-center gap-2 text-sm">
                        <Tag className="h-4 w-4 text-muted-foreground" />
                        <span>{item.brand}</span>
                      </div>
                    )}
                    {colorInfo && (
                      <div className="flex items-center gap-2 text-sm">
                        <Palette className="h-4 w-4 text-muted-foreground" />
                        <div
                          className="w-4 h-4 rounded-full border"
                          style={{ backgroundColor: colorInfo.hex }}
                        />
                        <span>{colorInfo.name}</span>
                      </div>
                    )}
                    {item.wear_count > 0 && (
                      <div className="flex items-center gap-2 text-sm">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        <span>
                          Worn {item.wear_count} time{item.wear_count !== 1 ? 's' : ''}
                          {item.last_worn_at && (
                            <span className="text-muted-foreground">
                              {' '}• Last: {new Date(item.last_worn_at).toLocaleDateString()}
                            </span>
                          )}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Wash Status */}
                  <div className="space-y-2 pt-2 border-t">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Droplets className={`h-4 w-4 ${item.needs_wash ? 'text-amber-500' : 'text-muted-foreground'}`} />
                        Wash Status
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={handleMarkWashed}
                        disabled={logWash.isPending}
                      >
                        {logWash.isPending ? (
                          <Loader2 className="h-3 w-3 animate-spin mr-1" />
                        ) : (
                          <Droplets className="h-3 w-3 mr-1" />
                        )}
                        Mark Washed
                      </Button>
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Wears since wash: {item.wears_since_wash}/{item.effective_wash_interval}</span>
                        {item.needs_wash && (
                          <span className="text-amber-500 font-medium">Needs washing</span>
                        )}
                      </div>
                      <Progress
                        value={Math.min((item.wears_since_wash / item.effective_wash_interval) * 100, 100)}
                        className={`h-2 ${item.needs_wash ? '[&>div]:bg-amber-500' : ''}`}
                      />
                      {item.last_washed_at && (
                        <p className="text-xs text-muted-foreground">
                          Last washed: {new Date(item.last_washed_at).toLocaleDateString()}
                        </p>
                      )}
                    </div>

                    {/* Wash History */}
                    {washHistory && washHistory.length > 0 && (
                      <Collapsible open={showWashHistory} onOpenChange={setShowWashHistory}>
                        <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                          <ChevronDown className={`h-3 w-3 transition-transform ${showWashHistory ? 'rotate-180' : ''}`} />
                          Wash history ({washHistory.length})
                        </CollapsibleTrigger>
                        <CollapsibleContent className="mt-1.5 space-y-1">
                          {washHistory.map((wash) => (
                            <div key={wash.id} className="text-xs text-muted-foreground flex items-center gap-2">
                              <span>{new Date(wash.washed_at).toLocaleDateString()}</span>
                              {wash.method && <Badge variant="outline" className="text-[10px] h-4">{wash.method}</Badge>}
                              {wash.notes && <span className="truncate">{wash.notes}</span>}
                            </div>
                          ))}
                        </CollapsibleContent>
                      </Collapsible>
                    )}
                  </div>

                  {/* Wear History */}
                  {item.wear_count > 0 && wearStats && (
                    <div className="space-y-2 pt-2 border-t">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        Wear History
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="bg-muted/50 rounded-md p-2">
                          <p className="text-muted-foreground">Total wears</p>
                          <p className="font-medium text-sm">{wearStats.total_wears}</p>
                        </div>
                        <div className="bg-muted/50 rounded-md p-2">
                          <p className="text-muted-foreground">Last worn</p>
                          <p className="font-medium text-sm">
                            {wearStats.days_since_last_worn === null
                              ? 'Never'
                              : wearStats.days_since_last_worn === 0
                              ? 'Today'
                              : `${wearStats.days_since_last_worn}d ago`}
                          </p>
                        </div>
                        <div className="bg-muted/50 rounded-md p-2">
                          <p className="text-muted-foreground">Avg/month</p>
                          <p className="font-medium text-sm">{wearStats.average_wears_per_month}</p>
                        </div>
                        {wearStats.most_common_occasion && (
                          <div className="bg-muted/50 rounded-md p-2">
                            <p className="text-muted-foreground">Usual occasion</p>
                            <p className="font-medium text-sm capitalize">{wearStats.most_common_occasion}</p>
                          </div>
                        )}
                      </div>

                      {/* Mini bar chart - wear by month */}
                      {Object.keys(wearStats.wear_by_month).length > 0 && (
                        <div className="space-y-1">
                          <p className="text-xs text-muted-foreground">Last 6 months</p>
                          <div className="flex items-end gap-1 h-12">
                            {Object.entries(wearStats.wear_by_month).map(([month, count]) => {
                              const maxCount = Math.max(...Object.values(wearStats.wear_by_month), 1);
                              const height = (count / maxCount) * 100;
                              return (
                                <div key={month} className="flex-1 flex flex-col items-center gap-0.5" title={`${month}: ${count} wears`}>
                                  <div
                                    className="w-full bg-primary/70 rounded-t-sm min-h-[2px]"
                                    style={{ height: `${Math.max(height, 4)}%` }}
                                  />
                                  <span className="text-[9px] text-muted-foreground">{month.split('-')[1]}</span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Wear timeline */}
                      {wearHistory && wearHistory.length > 0 && (
                        <Collapsible open={showWearHistory} onOpenChange={setShowWearHistory}>
                          <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                            <ChevronDown className={`h-3 w-3 transition-transform ${showWearHistory ? 'rotate-180' : ''}`} />
                            Timeline ({wearHistory.length} events)
                          </CollapsibleTrigger>
                          <CollapsibleContent className="mt-1.5 space-y-1.5">
                            {wearHistory.map((entry) => (
                              <div key={entry.id} className="text-xs flex items-start gap-2">
                                <span className="text-muted-foreground whitespace-nowrap">
                                  {new Date(entry.worn_at).toLocaleDateString()}
                                </span>
                                {entry.occasion && (
                                  <Badge variant="outline" className="text-[10px] h-4">{entry.occasion}</Badge>
                                )}
                                {entry.outfit && (
                                  <div className="flex -space-x-1">
                                    {entry.outfit.items.slice(0, 3).map((oi) => (
                                      <div
                                        key={oi.id}
                                        className="w-5 h-5 rounded-full bg-muted border-2 border-background overflow-hidden"
                                        title={oi.name || oi.type}
                                      >
                                        {oi.thumbnail_url && (
                                          <Image
                                            src={oi.thumbnail_url}
                                            alt={oi.name || oi.type}
                                            width={20}
                                            height={20}
                                            className="object-cover w-full h-full"
                                          />
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ))}
                          </CollapsibleContent>
                        </Collapsible>
                      )}
                    </div>
                  )}

                  {/* AI Analysis */}
                  {(hasAiTags || item.ai_description) && item.status === 'ready' && (
                    <div className="space-y-2 pt-2 border-t">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Sparkles className="h-4 w-4 text-primary" />
                        AI Analysis
                        {item.ai_confidence !== undefined && item.ai_confidence > 0 && (
                          <Badge variant="secondary" className="text-xs">
                            {Math.round(item.ai_confidence * 100)}% complete
                          </Badge>
                        )}
                        {item.tags?.logprobs_confidence != null && (
                          <Badge variant="outline" className="text-xs">
                            {Math.round(item.tags.logprobs_confidence * 100)}% confident
                          </Badge>
                        )}
                      </div>
                      {item.ai_description && (
                        <p className="text-sm text-muted-foreground italic">
                          &ldquo;{item.ai_description}&rdquo;
                        </p>
                      )}
                      {hasAiTags && <div className="flex flex-wrap gap-1.5">
                        {tags.colors?.map((color) => (
                          <Badge key={color} variant="outline" className="text-xs">
                            {color}
                          </Badge>
                        ))}
                        {tags.pattern && (
                          <Badge variant="outline" className="text-xs">
                            {tags.pattern}
                          </Badge>
                        )}
                        {tags.material && (
                          <Badge variant="outline" className="text-xs">
                            {tags.material}
                          </Badge>
                        )}
                        {tags.style?.map((s) => (
                          <Badge key={s} variant="outline" className="text-xs">
                            {s}
                          </Badge>
                        ))}
                        {tags.season?.map((s) => (
                          <Badge key={s} variant="outline" className="text-xs">
                            {s}
                          </Badge>
                        ))}
                        {tags.formality && (
                          <Badge variant="outline" className="text-xs">
                            {tags.formality}
                          </Badge>
                        )}
                        {tags.fit && (
                          <Badge variant="outline" className="text-xs">
                            {tags.fit} fit
                          </Badge>
                        )}
                        {tags.occasion?.map((o: string) => (
                          <Badge key={o} variant="outline" className="text-xs">
                            {o}
                          </Badge>
                        ))}
                        {tags.condition && (
                          <Badge variant="outline" className="text-xs">
                            {tags.condition}
                          </Badge>
                        )}
                        {tags.features?.map((f: string) => (
                          <Badge key={f} variant="outline" className="text-xs">
                            {f}
                          </Badge>
                        ))}
                      </div>}
                    </div>
                  )}

                  {/* Notes */}
                  {item.notes && (
                    <div className="space-y-1 pt-2 border-t">
                      <p className="text-sm font-medium">Notes</p>
                      <p className="text-sm text-muted-foreground">{item.notes}</p>
                    </div>
                  )}

                  {/* Metadata */}
                  <div className="text-xs text-muted-foreground pt-2 border-t">
                    Added {new Date(item.created_at).toLocaleDateString()}
                  </div>
                </div>
              )}
            </div>
            </div>

            {/* Delete button - separated from other actions for safety */}
            {!isEditing && (
              <div className="pt-4 border-t mt-4">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive hover:bg-destructive/10"
                  onClick={() => setShowDeleteConfirm(true)}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete this item
                </Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this item?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete &ldquo;{item.name || item.type}&rdquo; from your
              wardrobe. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteItem.isPending}
            >
              {deleteItem.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Generate Pairings Dialog */}
      <GeneratePairingsDialog
        item={item}
        open={showPairingsDialog}
        onOpenChange={setShowPairingsDialog}
      />
    </>
  );
}
