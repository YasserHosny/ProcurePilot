import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  provideAppInitializer,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { authInterceptor } from './core/auth/auth.interceptor';
import { restoreSessionOnStartup } from './core/auth/session-initializer';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    // Must run before the first navigation, or authGuard rejects a valid session.
    provideAppInitializer(restoreSessionOnStartup),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    // Synchronous rather than the async variant: pnpm's strict node_modules isolation stops
    // esbuild resolving platform-browser's dynamic import of @angular/animations/browser.
    provideAnimations(),
  ],
};
