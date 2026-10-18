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
import { CATEGORY_STYLES } from '@/components/item-photos/category-badge';
import { useGroupedClothingTypes } from '@/lib/hooks/use-translated-constants';
import type { ItemCategory } from '@/lib/types';

// The item type picker, split into clothing, footwear and accessories.
export function CategoryTypeSelect({
  value,
  onValueChange,
  placeholder,
  id,
  allLabel,
  only,
  className,
}: {
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  id?: string;
  // Adds an "all types" entry with the value 'all', for filters.
  allLabel?: string;
  // Limits the list to one section.
  only?: ItemCategory;
  className?: string;
}) {
  const groups = useGroupedClothingTypes().filter((group) => !only || group.category === only);
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger id={id} className={className}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allLabel && <SelectItem value="all">{allLabel}</SelectItem>}
        {groups.map((group) => (
          <SelectGroup key={group.category}>
            <SelectLabel className={CATEGORY_STYLES[group.category].text}>{group.label}</SelectLabel>
            {group.types.map((type) => (
              <SelectItem key={type.value} value={type.value}>
                {type.label}
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}
