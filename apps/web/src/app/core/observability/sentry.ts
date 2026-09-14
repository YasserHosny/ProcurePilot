import { ErrorHandler, Injectable, Provider } from '@angular/core';

import { environment } from '../../../environments/environment';

let sentryPromise: Promise<typeof import('@sentry/angular')> | null = null;

function loadSentry(): Promise<typeof import('@sentry/angular')> {
  if (!sentryPromise) {
    sentryPromise = import('@sentry/angular');
  }
  return sentryPromise;
}

/**
 * Browser error reporting — task T081 (FR-029).
 *
 * Initialised only when a DSN is configured, so local development runs without it. An absent DSN
 * is a valid state, not a misconfiguration.
 */
export function initErrorReporting(): void {
  const dsn = environment.sentryDsn;
  if (!dsn) {
    return;
  }

  void loadSentry().then((Sentry) => {
    Sentry.init({
      dsn,
      environment: environment.production ? 'production' : 'local',
      // Off by default: tracing and session replay both cost money per event and neither has an
      // agreed budget. Enable them deliberately rather than inheriting a library default.
      tracesSampleRate: 0,
      replaysSessionSampleRate: 0,
      // This application shows supplier pricing and personal data. Do not ship it to a third party.
      sendDefaultPii: false,
    });
  });
}

/** Routes uncaught Angular errors to Sentry when it is enabled. */
@Injectable()
export class LazySentryErrorHandler implements ErrorHandler {
  handleError(error: unknown): void {
    if (environment.sentryDsn) {
      void loadSentry()
        .then((Sentry) => {
          Sentry.captureException(error);
        })
        .catch(() => undefined);
    }
    console.error(error);
  }
}

export function provideErrorReporting(): Provider[] {
  return environment.sentryDsn
    ? [{ provide: ErrorHandler, useClass: LazySentryErrorHandler }]
    : [];
}
