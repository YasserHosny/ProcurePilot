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
import { SessionService } from './session.service';

/** Set on a request replayed after a refresh, so a second 401 signs out instead of looping. */
const REPLAYED_AFTER_REFRESH = new HttpContextToken<boolean>(() => false);

/** Endpoints whose 401 means "these credentials are wrong", never "renew and retry". */
const NO_REFRESH_PATHS = ['/auth/login', '/auth/refresh', '/auth/logout'];

/**
 * Attaches the bearer token and reacts to a rejected one.
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
    const sentToken = session.accessToken;
    const authorised = sentToken
      ? request.clone({ setHeaders: { Authorization: `Bearer ${sentToken}` } })
      : request;

    return next(authorised).pipe(
      catchError((error: unknown) => {
        if (!(error instanceof HttpErrorResponse) || error.status !== 401) {
          return throwError(() => error);
        }
        if (!mayRefresh(request) || !session.refreshToken) {
          signOut();
          return throwError(() => error);
        }
        const replay = request.clone({
          context: request.context.set(REPLAYED_AFTER_REFRESH, true),
        });
        // A refresh already landed while this request was out: replay with the new token.
        const current = session.accessToken;
        if (current && current !== sentToken) {
          return attempt(replay);
        }
        return session.refresh().pipe(
          catchError(() => {
            signOut();
            return throwError(() => error);
          }),
          switchMap(() => attempt(replay)),
        );
      }),
    );
  };

  return attempt(req);
};

function mayRefresh(req: HttpRequest<unknown>): boolean {
  if (req.context.get(REPLAYED_AFTER_REFRESH)) return false;
  const base = environment.apiBaseUrl;
  if (!req.url.startsWith(base)) return false;
  const path = req.url.slice(base.length).split('?')[0];
  return !NO_REFRESH_PATHS.includes(path);
}
