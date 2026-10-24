import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter } from '@angular/router';
import { MissingTranslationHandler, provideTranslateService } from '@ngx-translate/core';
import { provideTranslateHttpLoader } from '@ngx-translate/http-loader';

import { routes } from './app.routes';
import { provideErrorReporting } from './core/observability/sentry';
import { authInterceptor } from './core/auth/auth.interceptor';
import { restoreSessionOnStartup } from './core/auth/session-initializer';
import { AppMissingTranslationHandler, I18nService } from './core/i18n';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    // Must run before the first navigation, or authGuard rejects a valid session.
    provideAppInitializer(restoreSessionOnStartup),
    provideAppInitializer(() => {
      inject(I18nService);
    }),
    provideRouter(routes),
    provideHttpClient(withXhr(), withInterceptors([authInterceptor])),
    provideAnimationsAsync(),
    ...provideErrorReporting(),
    provideTranslateService({
      fallbackLang: 'en',
      // failOnError: a catalogue that fails to load (404, bad JSON) fails the language load, as
      // it did before ngx-translate 18, instead of being swapped for {} behind a console.warn.
      loader: provideTranslateHttpLoader({
        prefix: './assets/i18n/',
        suffix: '.json',
        failOnError: true,
      }),
      // An explicit useClass provider, not provideMissingTranslationHandler(Class): that helper
      // detects classes with /^class\s/ on the source text, which the minified `class{` fails,
      // so production builds called the constructor as a factory and crashed at bootstrap.
      missingTranslationHandler: {
        provide: MissingTranslationHandler,
        useClass: AppMissingTranslationHandler,
      },
    }),
  ],
};

