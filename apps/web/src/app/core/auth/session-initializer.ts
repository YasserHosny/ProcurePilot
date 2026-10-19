import { inject } from '@angular/core';
import { Observable, catchError, map, of } from 'rxjs';

import { SessionService, refreshWasRejected } from './session.service';

/**
 * Restores the session BEFORE the router runs its first navigation.
 *
 * Without this, a person who refreshes on a deep URL is bounced to sign-in even though their
 * token is perfectly valid: `authGuard` reads `isAuthenticated()` synchronously, and the restore
 * that would have made it true is still in flight. Doing it in AppComponent.ngOnInit is too
 * late — the guard has already decided.
 *
 * Found by the implementer reviewing the core code it was told not to modify, and correctly
 * reported rather than worked around in the screens.
 *
 * A stored access token that has expired (the tab sat closed for over an hour) is renewed from
 * the refresh token first, rather than spending a doomed /me call (demo finding 29).
 *
 * A failed restore resolves rather than rejects: an expired or revoked session means "not
 * signed in", which the guard handles, not a broken application.
 */
export function restoreSessionOnStartup(): Observable<null> {
  const session = inject(SessionService);

  if (!session.accessToken && !session.refreshToken) {
    return of(null);
  }

  const usedRefresh = !!session.refreshToken && session.accessTokenNeedsRefresh();
  const start: Observable<unknown> = usedRefresh ? session.refresh() : session.restore();

  return start.pipe(
    map(() => null),
    catchError((error: unknown) => {
      // A refused token ends the session. A refresh that was merely rate-limited or could not
      // reach the server keeps the tokens for the next load; the guard still sends the person
      // to sign-in for now, since no member was restored.
      if (refreshWasRejected(error)) session.logout();
      return of(null);
    }),
  );
}
