'use client';

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { colorSwatch } from '@/lib/colors';
import { useClothingColors, useColorFamilies, useColorLabel } from '@/lib/hooks/use-translated-constants';

// Radix Select cannot have an empty item value, so "no colour" is this placeholder.
const NONE = '__none__';

export function ColorSwatch({ color, className = 'w-3 h-3' }: { color: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={`inline-block shrink-0 rounded-full border ${className}`}
      style={{ backgroundColor: colorSwatch(color) }}
    />
  );
}

interface ColorSelectProps {
  id?: string;
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder?: string;
  // When set, the list starts with an entry that clears the colour.
  noneLabel?: string;
  // Shades already used elsewhere on the item (the primary colour, say) are left out.
  exclude?: readonly (string | null | undefined)[];
  disabled?: boolean;
  className?: string;
}

// Shades grouped under their family (Blues: navy, sapphire, sky blue...), so the long palette
// stays scannable; typing a name jumps to it.
export function ColorSelect({
  id,
  value,
  onChange,
  placeholder,
  noneLabel,
  exclude = [],
  disabled,
  className,
}: ColorSelectProps) {
  const shades = useClothingColors();
  const families = useColorFamilies();
  const colorLabel = useColorLabel();
  const offered = shades.filter((shade) => shade.value === value || !exclude.includes(shade.value));
  // A colour the palette does not offer (an older row, or a name from an API client) stays visible.
  const unlisted = value && !shades.some((shade) => shade.value === value) ? value : null;

  return (
    <Select
      value={value || (noneLabel ? NONE : '')}
      onValueChange={(next) => onChange(next === NONE ? null : next)}
      disabled={disabled}
    >
      <SelectTrigger id={id} className={className}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {noneLabel && <SelectItem value={NONE}>{noneLabel}</SelectItem>}
        {unlisted && (
          <SelectItem value={unlisted}>
            <div className="flex items-center gap-2">
              <ColorSwatch color={unlisted} />
              {colorLabel(unlisted)}
            </div>
          </SelectItem>
        )}
        {families.map((family) => {
          const members = offered.filter((shade) => shade.family === family.value);
          if (members.length === 0) return null;
          return (
            <SelectGroup key={family.value}>
              <SelectLabel className="flex items-center gap-2 pl-2 text-xs uppercase tracking-wide text-muted-foreground">
                <ColorSwatch color={family.value} />
                {family.name}
              </SelectLabel>
              {members.map((shade) => (
                <SelectItem key={shade.value} value={shade.value}>
                  <div className="flex items-center gap-2">
                    <ColorSwatch color={shade.value} />
                    {shade.name}
                  </div>
                </SelectItem>
              ))}
            </SelectGroup>
          );
        })}
      </SelectContent>
    </Select>
  );
}
