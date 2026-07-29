import { cookies, headers } from 'next/headers';
import { getRequestConfig } from 'next-intl/server';
import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  NAMESPACES,
  isValidLocale,
  resolveLocale,
  type Namespace,
  type SupportedLocale,
} from '@/lib/i18n/locales';

type Messages = Record<string, Record<string, unknown>>;

// Template-literal import so webpack bundles every messages/<locale>/<ns>.json into the build.
// A runtime fs.readFileSync would not survive `output: 'standalone'`, which copies only the
// traced bundle plus .next/static.
async function loadNamespace(locale: string, namespace: Namespace): Promise<Record<string, unknown>> {
  return (await import(`../messages/${locale}/${namespace}.json`)).default;
}

async function loadMessages(locale: SupportedLocale): Promise<Messages> {
  const messages: Messages = {};

  for (const namespace of NAMESPACES) {
    const english = await loadNamespace(DEFAULT_LOCALE, namespace);

    if (locale === DEFAULT_LOCALE) {
      messages[namespace] = english;
      continue;
    }

    try {
      // English underlies every namespace so a key still awaiting translation renders its
      // English text rather than a raw key path.
      messages[namespace] = { ...english, ...(await loadNamespace(locale, namespace)) };
    } catch {
      messages[namespace] = english;
    }
  }

  return messages;
}

async function detectLocale(): Promise<SupportedLocale> {
  let cookieLocale: string | undefined;
  try {
    cookieLocale = (await cookies()).get(LOCALE_COOKIE)?.value;
  } catch {
    cookieLocale = undefined;
  }
  if (isValidLocale(cookieLocale)) return cookieLocale;

  // No explicit choice stored yet, so honour the browser's preference on first visit.
  let acceptLanguage: string | null = null;
  try {
    acceptLanguage = (await headers()).get('accept-language');
  } catch {
    acceptLanguage = null;
  }
  if (!acceptLanguage) return DEFAULT_LOCALE;

  const preferences = acceptLanguage
    .split(',')
    .map((part) => {
      const [tag, ...params] = part.trim().split(';');
      const q = params.find((p) => p.trim().startsWith('q='));
      return { tag: tag.trim(), quality: q ? Number.parseFloat(q.split('=')[1]) || 0 : 1 };
    })
    .filter((p) => p.tag && p.tag !== '*')
    .sort((a, b) => b.quality - a.quality);

  for (const { tag } of preferences) {
    if (tag.toLowerCase().split('-')[0] === 'en') return DEFAULT_LOCALE;
    const resolved = resolveLocale(tag);
    if (resolved !== DEFAULT_LOCALE) return resolved;
  }

  return DEFAULT_LOCALE;
}

export default getRequestConfig(async () => {
  const locale = await detectLocale();

  return {
    locale,
    messages: await loadMessages(locale),
  };
});
