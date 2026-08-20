import enCatalog from './en.json';
import arCatalog from './ar.json';

export type SupportedLocale = 'en' | 'ar';

export const SUPPORTED_LOCALES: readonly SupportedLocale[] = ['en', 'ar'] as const;
export const DEFAULT_LOCALE: SupportedLocale = 'en';
export const RTL_LOCALES: readonly SupportedLocale[] = ['ar'] as const;

export function isRtlLocale(locale: string | null | undefined): boolean {
  if (!locale) return false;
  return RTL_LOCALES.includes(locale as SupportedLocale);
}

export { enCatalog, arCatalog };
