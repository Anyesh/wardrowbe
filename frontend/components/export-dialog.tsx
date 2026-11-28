'use client';

import { useEffect, useState } from 'react';
import { Check, Code2, Copy, Download, FileText, Layers, Loader2, Sparkles } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api';
import { useDescribeError } from '@/lib/errors';
import type { BulkItemFilters, BulkOperationParams } from '@/lib/hooks/use-items';
import {
  useColorLabel,
  useFitLabel,
  useFormalityLabel,
  useMaterialLabel,
  usePatternLabel,
  useSeasonLabel,
  useStyleLabel,
  useSubtypeLabel,
  useTypeLabel,
} from '@/lib/hooks/use-translated-constants';
import { cn } from '@/lib/utils';
import {
  type CatalogueFormat,
  type CatalogueLabels,
  type ExportFileTranslator,
  renderCatalogue,
  type WardrobeExport,
} from '@/lib/wardrobe-export';

type ServerFormat = 'skill' | 'json';
export type ExportFormat = ServerFormat | CatalogueFormat;

const FILES: Record<ExportFormat, { filename: string; type: string }> = {
  skill: { filename: 'SKILL.md', type: 'text/markdown;charset=utf-8' },
  markdown: { filename: 'wardrobe.md', type: 'text/markdown;charset=utf-8' },
  text: { filename: 'wardrobe.txt', type: 'text/plain;charset=utf-8' },
  json: { filename: 'wardrobe.json', type: 'application/json' },
};

const FORMATS: { id: ExportFormat; icon: typeof Sparkles }[] = [
  { id: 'skill', icon: Sparkles },
  { id: 'markdown', icon: FileText },
  { id: 'text', icon: Layers },
  { id: 'json', icon: Code2 },
];

interface ExportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  viewFilters: BulkItemFilters;
  totalCount: number;
  selection: BulkOperationParams | null;
  selectedCount: number;
}

function isCatalogue(format: ExportFormat): format is CatalogueFormat {
  return format === 'markdown' || format === 'text';
}

function exportRequest(
  format: ServerFormat,
  includeProfile: boolean,
  selection: BulkOperationParams | null,
  viewFilters: BulkItemFilters
) {
  const body = { format, include_profile: includeProfile };
  if (!selection) return { ...body, filters: viewFilters };
  if (selection.select_all) {
    return { ...body, filters: selection.filters, excluded_ids: selection.excluded_ids };
  }
  return { ...body, item_ids: selection.item_ids };
}

function useCatalogueLabels(): CatalogueLabels {
  const t: ExportFileTranslator = useTranslations('wardrobe.exportFile');
  const locale = useLocale();
  const type = useTypeLabel();
  const subtype = useSubtypeLabel();
  const color = useColorLabel();
  const material = useMaterialLabel();
  const pattern = usePatternLabel();
  const formality = useFormalityLabel();
  const style = useStyleLabel();
  const season = useSeasonLabel();
  const fit = useFitLabel();
  return { t, locale, type, subtype, color, material, pattern, formality, style, season, fit };
}

export function ExportDialog({
  open,
  onOpenChange,
  viewFilters,
  totalCount,
  selection,
  selectedCount,
}: ExportDialogProps) {
  const t = useTranslations('wardrobe.exportDialog');
  const describeError = useDescribeError();
  const catalogueLabels = useCatalogueLabels();
  const [format, setFormat] = useState<ExportFormat>('skill');
  const [onlySelected, setOnlySelected] = useState(false);
  const [includeProfile, setIncludeProfile] = useState(true);
  const [busy, setBusy] = useState<'download' | 'copy' | null>(null);
  const [copied, setCopied] = useState(false);

  const hasSelection = selection !== null;
  useEffect(() => {
    if (open) setOnlySelected(hasSelection);
  }, [open, hasSelection]);

  const fetchExport = async () => {
    const scope = onlySelected ? selection : null;
    if (isCatalogue(format)) {
      const data = await api.post<WardrobeExport>(
        '/items/export',
        exportRequest('json', false, scope, viewFilters)
      );
      return renderCatalogue(data, format, catalogueLabels);
    }
    return api.postForText('/items/export', exportRequest(format, includeProfile, scope, viewFilters));
  };

  const handleDownload = async () => {
    setBusy('download');
    try {
      const content = await fetchExport();
      const { filename, type } = FILES[format];
      const url = URL.createObjectURL(new Blob([content], { type }));
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      // Some browsers resolve the blob URL after click() returns, so it is freed a moment later.
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(t('downloaded', { filename }));
    } catch (error) {
      toast.error(describeError(error, t('failed')));
    } finally {
      setBusy(null);
    }
  };

  const handleCopy = async () => {
    setBusy('copy');
    try {
      await navigator.clipboard.writeText(await fetchExport());
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
      toast.success(t('copied'));
    } catch (error) {
      toast.error(describeError(error, t('failed')));
    } finally {
      setBusy(null);
    }
  };

  const profileApplies = !isCatalogue(format);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-5 py-2 pr-1">
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium mb-2">{t('format')}</legend>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {FORMATS.map(({ id, icon: Icon }) => {
                const selected = format === id;
                return (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setFormat(id)}
                    className={cn(
                      'text-left p-3 rounded-lg border transition-colors',
                      selected
                        ? 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'border-border hover:bg-muted/50'
                    )}
                  >
                    <span className="flex items-center gap-1.5 font-medium text-sm mb-1">
                      <Icon
                        className={cn('h-4 w-4', selected ? 'text-primary' : 'text-muted-foreground')}
                      />
                      {t(`formats.${id}.name`)}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {t(`formats.${id}.description`)}
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>

          {selection && (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium mb-2">{t('scope')}</legend>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  aria-pressed={onlySelected}
                  variant={onlySelected ? 'default' : 'outline'}
                  onClick={() => setOnlySelected(true)}
                >
                  {t('scopeSelected', { count: selectedCount })}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  aria-pressed={!onlySelected}
                  variant={onlySelected ? 'outline' : 'default'}
                  onClick={() => setOnlySelected(false)}
                >
                  {t('scopeAll', { count: totalCount })}
                </Button>
              </div>
            </fieldset>
          )}

          {profileApplies && (
            <div className="flex items-start gap-2">
              <Checkbox
                id="export-include-profile"
                checked={includeProfile}
                onCheckedChange={(checked) => setIncludeProfile(checked === true)}
              />
              <Label htmlFor="export-include-profile" className="text-sm leading-snug">
                {t('includeProfile')}
              </Label>
            </div>
          )}

          {format === 'skill' && (
            <p className="rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
              {t('skillHowTo')}
            </p>
          )}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2 pt-2 border-t">
          <Button type="button" variant="outline" onClick={handleCopy} disabled={busy !== null}>
            {busy === 'copy' ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : copied ? (
              <Check className="mr-1.5 h-4 w-4" />
            ) : (
              <Copy className="mr-1.5 h-4 w-4" />
            )}
            {copied ? t('copied') : t('copy')}
          </Button>
          <Button type="button" onClick={handleDownload} disabled={busy !== null}>
            {busy === 'download' ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-1.5 h-4 w-4" />
            )}
            {t('download')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
