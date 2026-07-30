export const SUPPORTED_LOCALES = ['en', 'zh-CN', 'zh-TW', 'ko', 'ja', 'fr', 'de', 'it'] as const;

export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: SupportedLocale = 'en';

export const LOCALE_COOKIE = 'NEXT_LOCALE';

export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

export const LOCALE_METADATA: Record<SupportedLocale, { name: string; nativeName: string; dir: 'ltr' | 'rtl' }> = {
  en: { name: 'English', nativeName: 'English', dir: 'ltr' },
  'zh-CN': { name: 'Chinese (Simplified)', nativeName: '中文简体', dir: 'ltr' },
  'zh-TW': { name: 'Chinese (Traditional)', nativeName: '中文繁體', dir: 'ltr' },
  ko: { name: 'Korean', nativeName: '한국어', dir: 'ltr' },
  ja: { name: 'Japanese', nativeName: '日本語', dir: 'ltr' },
  fr: { name: 'French', nativeName: 'Français', dir: 'ltr' },
  de: { name: 'German', nativeName: 'Deutsch', dir: 'ltr' },
  it: { name: 'Italian', nativeName: 'Italiano', dir: 'ltr' },
};

export const NAMESPACES = [
  'common',
  'nav',
  'auth',
  'onboarding',
  'dashboard',
  'wardrobe',
  'suggest',
  'history',
  'settings',
  'family',
  'notifications',
  'analytics',
  'learning',
  'pairings',
  'outfits',
  'constants',
  'errors',
] as const;

export type Namespace = (typeof NAMESPACES)[number];

export function isValidLocale(locale: string | undefined | null): locale is SupportedLocale {
  return !!locale && (SUPPORTED_LOCALES as readonly string[]).includes(locale);
}

/** Maps a browser Accept-Language tag onto a supported locale: exact match first, then the
 *  base language, so `de-AT` resolves to `de` and `zh-HK` to `zh-TW` rather than to English. */
export function resolveLocale(candidate: string | undefined | null): SupportedLocale {
  if (!candidate) return DEFAULT_LOCALE;
  if (isValidLocale(candidate)) return candidate;

  const lower = candidate.toLowerCase();
  const exact = SUPPORTED_LOCALES.find((l) => l.toLowerCase() === lower);
  if (exact) return exact;

  if (lower.startsWith('zh')) {
    return /hant|tw|hk|mo/.test(lower) ? 'zh-TW' : 'zh-CN';
  }

  const base = lower.split('-')[0];
  const byBase = SUPPORTED_LOCALES.find((l) => l.toLowerCase().split('-')[0] === base);
  return byBase ?? DEFAULT_LOCALE;
}
