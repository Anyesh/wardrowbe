import {cookies} from 'next/headers';
import {getRequestConfig} from 'next-intl/server';

const SUPPORTED_LOCALES = ['en', 'zh', 'fr', 'it'] as const;

export default getRequestConfig(async () => {
  let cookieLocale: string | undefined;
  try {
    const store = await cookies();
    cookieLocale = store.get('NEXT_LOCALE')?.value;
  } catch {
    cookieLocale = undefined;
  }

  const locale = cookieLocale && (SUPPORTED_LOCALES as readonly string[]).includes(cookieLocale) ? cookieLocale : 'en';

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default
  };
});
