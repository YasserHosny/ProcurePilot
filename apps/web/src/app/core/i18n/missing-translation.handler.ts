import { isDevMode } from '@angular/core';
import {
  MissingTranslationHandler,
  MissingTranslationHandlerParams,
} from '@ngx-translate/core';

/**
 * Custom MissingTranslationHandler that fails loudly in development.
 *
 * SC-005 & T063: A missing translation key must be detectable in development
 * rather than silently rendering as a raw key to a customer.
 */
export class AppMissingTranslationHandler implements MissingTranslationHandler {
  handle(params: MissingTranslationHandlerParams): string {
    const key = params.key;
    const currentLang = params.translateService.currentLang || params.translateService.defaultLang || 'en';
    const message = `[i18n] MISSING TRANSLATION: Key "${key}" not found in locale "${currentLang}".`;

    if (isDevMode()) {
      console.error(message);
      return `[MISSING: ${key}]`;
    }

    return key;
  }
}
