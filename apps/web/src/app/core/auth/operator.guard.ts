import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';

import { OperatorService } from './operator.service';

/**
 * Guards platform-operator routes. A navigation convenience, NOT a security control: the API
 * answers every `/platform/*` request with 404 unless the caller is a live platform operator.
 */
export const operatorGuard: CanActivateFn = () => {
  const operator = inject(OperatorService);
  const router = inject(Router);
  return operator.load().pipe(map((profile) => (profile ? true : router.createUrlTree(['/']))));
};
