import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { SessionService } from './session.service';

/**
 * Attaches the bearer token and reacts to a rejected one.
 *
 * A 401 means the token is invalid, expired, or the membership behind it was removed — the
 * server re-checks membership status on every request, so a removed member loses access at
 * once rather than at token expiry. Either way the client's only correct response is to drop
 * the session and send the person to sign-in.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const session = inject(SessionService);
  const router = inject(Router);

  const token = session.accessToken;
  const authorised = token
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(authorised).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 401) {
        session.logout();
        void router.navigate(['/auth/sign-in']);
      }
      return throwError(() => error);
    }),
  );
};
