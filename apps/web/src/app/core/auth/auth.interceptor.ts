import {
  HttpContextToken,
  HttpErrorResponse,
  HttpEvent,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, switchMap, throwError } from 'rxjs';

import { environment } from '../../../environments/environment';
import { REBUILD_ON_REPLAY, SEND_SESSION_TOKEN } from './http-context';
import { SessionService, refreshWasRejected, tokenTenant } from './session.service';

/** Set on a request replayed after a refresh, so a second 401 signs out instead of looping. */
const REPLAYED_AFTER_REFRESH = new HttpContextToken<boolean>(() => false);

/** Endpoints whose 401 means "these credentials are wrong", never "renew and retry". */
const NO_REFRESH_PATHS = ['/auth/login', '/auth/refresh', '/auth/logout'];

/**
 * Attaches the bearer token to OUR API's requests only, and reacts to a rejected one.
 *
 * A 401 from our API usually means the hour-long access token expired (demo finding 29), so the
 * first response is to renew it once from the refresh token and replay the request. Parallel
 * 401s share the single in-flight refresh in SessionService.
 *
 * If the refresh fails, or the replayed request is still refused, the session really is over:
 * the token was revoked, or the membership behind it was removed (the server re-checks
 * membership status on every request, so a removed member loses access at once). Then the only
 * correct response is to drop the session and send the person to sign-in.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const session = inject(SessionService);
  const router = inject(Router);

  const signOut = (): void => {
    session.logout();
    void router.navigate(['/auth/sign-in']);
  };

  const attempt = (request: HttpRequest<unknown>): Observable<HttpEvent<unknown>> => {
    // Only our API gets the bearer token by default. Anything else — a translation file, a
    // third-party URL — must never see it, and its 401 says nothing about our session.
    // A server-issued upload target may opt in to the token, but its 401 still does not touch
    // the session.
    if (!isOwnApi(request.url)) {
      const token = request.context.get(SEND_SESSION_TOKEN) ? session.accessToken : null;
      return next(token ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : request);
    }
    const sentToken = session.accessToken;
    const authorised = sentToken
      ? request.clone({ setHeaders: { Authorization: `Bearer ${sentToken}` } })
      : request;

    return next(authorised).pipe(
      catchError((error: unknown) => {
        if (!(error instanceof HttpErrorResponse) || error.status !== 401) {
          return throwError(() => error);
        }
        // Credential endpoints own their errors. In particular, a refresh 401 must reach
        // SessionService before anything clears storage, so it can retry a rotated token.
        if (NO_REFRESH_PATHS.includes(apiPath(request.url))) return throwError(() => error);
        if (!mayRefresh(request) || !session.refreshToken) {
          signOut();
          return throwError(() => error);
        }
        const rebuild = request.context.get(REBUILD_ON_REPLAY);
        const marked = request.clone({
          context: request.context.set(REPLAYED_AFTER_REFRESH, true),
        });
        // Rebuilt lazily, after the refresh, so it sees the rotated refresh token.
        const replay = (): HttpRequest<unknown> => (rebuild ? rebuild(marked) : marked);
        // The token decides the workspace, so a request is only replayed under the workspace it
        // was sent for. If a switch landed meanwhile, it fails instead of running in the new one.
        const replayInSameWorkspace = (): Observable<HttpEvent<unknown>> =>
          tokenTenant(session.accessToken) === tokenTenant(sentToken)
            ? attempt(replay())
            : throwError(() => error);
        // A refresh already landed while this request was out: replay with the new token.
        const current = session.accessToken;
        if (current && current !== sentToken) {
          return replayInSameWorkspace();
        }
        return session.refresh(rebuild !== null).pipe(
          catchError((refreshError: unknown) => {
            // A rate-limited or unreachable refresh leaves the session intact; only a refused
            // refresh token ends it.
            if (refreshWasRejected(refreshError)) signOut();
            return throwError(() => error);
          }),
          switchMap(() => replayInSameWorkspace()),
        );
      }),
    );
  };

  return attempt(req);
};

function isOwnApi(url: string): boolean {
  const base = environment.apiBaseUrl;
  return url === base || url.startsWith(`${base}/`) || url.startsWith(`${base}?`);
}

function mayRefresh(req: HttpRequest<unknown>): boolean {
  if (req.context.get(REPLAYED_AFTER_REFRESH)) return false;
  return !NO_REFRESH_PATHS.includes(apiPath(req.url));
}

function apiPath(url: string): string {
  return url.slice(environment.apiBaseUrl.length).split('?')[0];
}
