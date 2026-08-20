import { ErrorHandler, Provider } from '@angular/core';
import * as Sentry from '@sentry/angular';

import { environment } from '../../../environments/environment';

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
}

/** Routes uncaught Angular errors to Sentry when it is enabled. */
export function provideErrorReporting(): Provider[] {
  return environment.sentryDsn
    ? [{ provide: ErrorHandler, useValue: Sentry.createErrorHandler() }]
    : [];
}
