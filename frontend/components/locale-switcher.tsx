'use client';

import { useTransition } from 'react';
import { useLocale } from 'next-intl';
import { Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTranslations } from 'next-intl';

const LOCALES = [
  { value: 'en', label: 'English' },
  { value: 'zh', label: '中文' },
  { value: 'fr', label: 'Français' },
  { value: 'it', label: 'Italiano' },
] as const;

export function LocaleSwitcher() {
  const t = useTranslations('shared.localeSwitcher');
  const currentLocale = useLocale();
  const [isPending, startTransition] = useTransition();

  const handleChange = (nextLocale: string) => {
    document.cookie = `NEXT_LOCALE=${nextLocale};path=/;max-age=${60 * 60 * 24 * 365};SameSite=Lax`;
    startTransition(() => {
      window.location.reload();
    });
  };

  const currentLabel = LOCALES.find((l) => l.value === currentLocale)?.label ?? currentLocale;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t('label')}
          disabled={isPending}
        >
          <Globe className="h-5 w-5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {LOCALES.map((locale) => (
          <DropdownMenuItem
            key={locale.value}
            onClick={() => handleChange(locale.value)}
            className={currentLocale === locale.value ? 'bg-accent' : ''}
          >
            {locale.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
