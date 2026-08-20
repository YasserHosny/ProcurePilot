import { inject } from '@angular/core';
import { catchError, of } from 'rxjs';

import { SessionService } from './session.service';

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
 * A failed restore resolves rather than rejects: an expired or revoked token means "not signed
 * in", which the guard handles, not a broken application.
 */
export function restoreSessionOnStartup() {
  const session = inject(SessionService);

  if (!session.accessToken) {
    return of(null);
  }

  return session.restore().pipe(
    catchError(() => {
      session.logout();
      return of(null);
    }),
  );
}
