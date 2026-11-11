'use client';

import { useTranslations } from 'next-intl';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

// Radix Select cannot have an empty item value, so "no model" is this placeholder.
const NONE = '__none__';

interface AIModelSelectProps {
  id?: string;
  value: string | null;
  onChange: (value: string | null) => void;
  // What the server listed when its connection was tested, split by the name heuristic.
  visionModels: readonly string[];
  textModels: readonly string[];
  // The kind this field asks for, listed first.
  kind: 'vision' | 'text';
}

// Offered once a connection test has listed the server's models, in place of typing a name.
// "None" leaves the endpoint out for this kind of request.
export function AIModelSelect({ id, value, onChange, visionModels, textModels, kind }: AIModelSelectProps) {
  const t = useTranslations('settings.aiEndpoints');
  const groups = [
    { key: 'vision', label: t('visionGroup'), models: visionModels },
    { key: 'text', label: t('textGroup'), models: textModels },
  ];
  if (kind === 'text') groups.reverse();
  const listed = value !== null && [...visionModels, ...textModels].includes(value);

  return (
    <Select value={value ?? NONE} onValueChange={(next) => onChange(next === NONE ? null : next)}>
      <SelectTrigger id={id} className="h-8">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{t('modelNone')}</SelectItem>
        {/* A saved model the server no longer lists stays visible, so it is not silently dropped. */}
        {value !== null && !listed && (
          <SelectItem value={value}>{t('modelUnavailable', { model: value })}</SelectItem>
        )}
        {groups
          .filter((group) => group.models.length > 0)
          .map((group) => (
            <SelectGroup key={group.key}>
              <SelectLabel className="pl-2 text-xs text-muted-foreground">{group.label}</SelectLabel>
              {group.models.map((model) => (
                <SelectItem key={model} value={model}>
                  {model}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
      </SelectContent>
    </Select>
  );
}
