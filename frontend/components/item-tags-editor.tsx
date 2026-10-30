'use client';

import { useId } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  FIT_VALUES,
  FORMALITY_VALUES,
  ITEM_STYLE_VALUES,
  MATERIAL_VALUES,
  PATTERN_VALUES,
  SEASON_VALUES,
} from '@/lib/generated/garment-vocabulary';
import {
  useClothingColors,
  useFitLabel,
  useFormalityLabel,
  useMaterialLabel,
  usePatternLabel,
  useSeasonLabel,
  useStyleLabel,
} from '@/lib/hooks/use-translated-constants';
import type { TagDraft } from '@/lib/tag-edits';

// Radix Select cannot have an empty item value, so "no value" is this placeholder.
const NONE = '__none__';

interface Option {
  value: string;
  label: string;
  hex?: string;
}

interface TagSelectProps {
  label: string;
  noneLabel: string;
  value: string | null;
  options: readonly Option[];
  onChange: (value: string | null) => void;
  describe?: (value: string) => string;
  disabled?: boolean;
}

function TagSelect({ label, noneLabel, value, options, onChange, describe, disabled }: TagSelectProps) {
  const id = useId();
  // A value the list does not offer (an older row, or a colour name from an API client) stays visible.
  const shown =
    value && !options.some((option) => option.value === value)
      ? [...options, { value, label: describe ? describe(value) : value }]
      : options;

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Select
        value={value ?? NONE}
        onValueChange={(next) => onChange(next === NONE ? null : next)}
        disabled={disabled}
      >
        <SelectTrigger id={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>{noneLabel}</SelectItem>
          {shown.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.hex ? (
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full border" style={{ backgroundColor: option.hex }} />
                  {option.label}
                </div>
              ) : (
                option.label
              )}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

interface ChipGroupProps {
  label: string;
  values: readonly string[];
  selected: readonly string[];
  labelFor: (value: string) => string;
  onChange: (selected: string[]) => void;
}

function ChipGroup({ label, values, selected, labelFor, onChange }: ChipGroupProps) {
  // Values already on the item that the list no longer offers can still be switched off.
  const all = [...values, ...selected.filter((value) => !values.includes(value))];
  return (
    <div className="space-y-2" role="group" aria-label={label}>
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-1.5">
        {all.map((value) => {
          const on = selected.includes(value);
          return (
            <Button
              key={value}
              type="button"
              size="sm"
              variant={on ? 'default' : 'outline'}
              aria-pressed={on}
              onClick={() => onChange(on ? selected.filter((s) => s !== value) : [...selected, value])}
            >
              {labelFor(value)}
            </Button>
          );
        })}
      </div>
    </div>
  );
}

interface ItemTagsEditorProps {
  draft: TagDraft;
  onChange: (draft: TagDraft) => void;
  // The item's primary colour as set in the edit form, which the extra colours must not repeat.
  primaryColor?: string;
}

export function ItemTagsEditor({ draft, onChange, primaryColor }: ItemTagsEditorProps) {
  const t = useTranslations('wardrobe.itemDetail.tagsEditor');
  const patternLabel = usePatternLabel();
  const materialLabel = useMaterialLabel();
  const formalityLabel = useFormalityLabel();
  const fitLabel = useFitLabel();
  const styleLabel = useStyleLabel();
  const seasonLabel = useSeasonLabel();
  const clothingColors = useClothingColors();

  const labelled = (values: readonly string[], labelFor: (value: string) => string): Option[] =>
    values.map((value) => ({ value, label: labelFor(value) }));

  const [secondary = null, tertiary = null] = draft.extraColors;
  const colorOptions = (taken: (string | null | undefined)[]): Option[] =>
    clothingColors
      .filter((color) => !taken.includes(color.value))
      .map((color) => ({ value: color.value, label: color.name, hex: color.hex }));
  const colorName = (value: string) => clothingColors.find((c) => c.value === value)?.name ?? value;

  // Picking "None" for the secondary colour moves the tertiary colour up, so there is never a gap.
  const setExtraColor = (index: number, value: string | null) => {
    const next = [...draft.extraColors];
    if (value) next[index] = value;
    else next.splice(index, 1);
    onChange({ ...draft, extraColors: next });
  };

  return (
    <div className="space-y-4 border-t pt-4">
      <div>
        <h3 className="text-sm font-medium">{t('title')}</h3>
        <p className="text-xs text-muted-foreground">{t('hint')}</p>
      </div>

      <TagSelect
        label={t('pattern')}
        noneLabel={t('none')}
        value={draft.pattern}
        options={labelled(PATTERN_VALUES, patternLabel)}
        describe={patternLabel}
        onChange={(pattern) => onChange({ ...draft, pattern })}
      />
      <TagSelect
        label={t('material')}
        noneLabel={t('none')}
        value={draft.material}
        options={labelled(MATERIAL_VALUES, materialLabel)}
        describe={materialLabel}
        onChange={(material) => onChange({ ...draft, material })}
      />
      <TagSelect
        label={t('formality')}
        noneLabel={t('none')}
        value={draft.formality}
        options={labelled(FORMALITY_VALUES, formalityLabel)}
        describe={formalityLabel}
        onChange={(formality) => onChange({ ...draft, formality })}
      />
      <TagSelect
        label={t('fit')}
        noneLabel={t('none')}
        value={draft.fit}
        options={labelled(FIT_VALUES, fitLabel)}
        describe={fitLabel}
        onChange={(fit) => onChange({ ...draft, fit })}
      />

      <ChipGroup
        label={t('style')}
        values={ITEM_STYLE_VALUES}
        selected={draft.style}
        labelFor={styleLabel}
        onChange={(style) => onChange({ ...draft, style })}
      />
      <ChipGroup
        label={t('season')}
        values={SEASON_VALUES}
        selected={draft.season}
        labelFor={seasonLabel}
        onChange={(season) => onChange({ ...draft, season })}
      />

      <TagSelect
        label={t('secondaryColor')}
        noneLabel={t('none')}
        value={secondary}
        options={colorOptions([primaryColor, tertiary])}
        describe={colorName}
        onChange={(value) => setExtraColor(0, value)}
      />
      {secondary && (
        <TagSelect
          label={t('tertiaryColor')}
          noneLabel={t('none')}
          value={tertiary}
          options={colorOptions([primaryColor, secondary])}
          describe={colorName}
          onChange={(value) => setExtraColor(1, value)}
        />
      )}
    </div>
  );
}
