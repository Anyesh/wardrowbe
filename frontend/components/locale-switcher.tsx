'use client';

import { useTransition } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { Check, Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useUpdateUserProfile } from '@/lib/hooks/use-user';
import {
  LOCALE_COOKIE,
  LOCALE_COOKIE_MAX_AGE,
  LOCALE_METADATA,
  SUPPORTED_LOCALES,
  type SupportedLocale,
} from '@/lib/i18n/locales';

export function LocaleSwitcher() {
  const t = useTranslations('nav');
  const currentLocale = useLocale();
  const router = useRouter();
  const { status } = useSession();
  const updateProfile = useUpdateUserProfile();
  const [isPending, startTransition] = useTransition();

  const handleChange = (nextLocale: SupportedLocale) => {
    if (nextLocale === currentLocale) return;

    // The cookie is what the server reads on the next render, so it must be set before the
    // refresh. Persisting to the profile is best-effort, so the choice follows the user to
    // another browser, but a failure there must not block the language from actually changing.
    document.cookie = `${LOCALE_COOKIE}=${nextLocale};path=/;max-age=${LOCALE_COOKIE_MAX_AGE};SameSite=Lax`;

    if (status === 'authenticated') {
      updateProfile.mutate({ locale: nextLocale });
    }

    startTransition(() => {
      router.refresh();
    });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t('changeLanguage')} disabled={isPending}>
          <Globe className="h-5 w-5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {SUPPORTED_LOCALES.map((locale) => (
          <DropdownMenuItem
            key={locale}
            onClick={() => handleChange(locale)}
            lang={locale}
            className="flex items-center justify-between gap-3"
          >
            <span>{LOCALE_METADATA[locale].nativeName}</span>
            {locale === currentLocale && <Check className="h-4 w-4 shrink-0" aria-hidden="true" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
