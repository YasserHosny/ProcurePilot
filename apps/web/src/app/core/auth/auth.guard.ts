import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import type { Role } from '../api/models';
import { SessionService } from './session.service';

/** Guards routes that require a signed-in member. */
export const authGuard: CanActivateFn = (_route, state) => {
  const session = inject(SessionService);
  const router = inject(Router);

  if (session.isAuthenticated()) {
    return true;
  }
  return router.createUrlTree(['/auth/sign-in'], {
    queryParams: { returnUrl: state.url },
  });
};

/**
 * Guards routes restricted to particular roles.
 *
 * This is a navigation convenience, NOT a security control — the server refuses the action
 * regardless (research R9). Never let this be the only thing standing between a role and an
 * action it may not perform.
 */
export const roleGuard = (...roles: readonly Role[]): CanActivateFn => {
  return () => {
    const session = inject(SessionService);
    const router = inject(Router);
    return session.hasRole(...roles) ? true : router.createUrlTree(['/']);
  };
};
