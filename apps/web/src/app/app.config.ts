import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter } from '@angular/router';
import {
  MissingTranslationHandler,
  TranslateLoader,
  provideTranslateService,
} from '@ngx-translate/core';

import { routes } from './app.routes';
import { provideErrorReporting } from './core/observability/sentry';
import { authInterceptor } from './core/auth/auth.interceptor';
import { restoreSessionOnStartup } from './core/auth/session-initializer';
import {
  AppMissingTranslationHandler,
  I18nService,
  httpLoaderFactory,
} from './core/i18n';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    // Must run before the first navigation, or authGuard rejects a valid session.
    provideAppInitializer(restoreSessionOnStartup),
    provideAppInitializer(() => {
      inject(I18nService);
    }),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideAnimationsAsync(),
    ...provideErrorReporting(),
    provideTranslateService({
      defaultLanguage: 'en',
      loader: {
        provide: TranslateLoader,
        useFactory: httpLoaderFactory,
        deps: [HttpClient],
      },
      missingTranslationHandler: {
        provide: MissingTranslationHandler,
        useClass: AppMissingTranslationHandler,
      },
    }),
  ],
};

