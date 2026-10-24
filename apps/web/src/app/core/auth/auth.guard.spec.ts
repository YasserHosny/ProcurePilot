import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree } from '@angular/router';

import { authGuard, guestGuard } from './auth.guard';
import { SessionService } from './session.service';

describe('authGuard and guestGuard', () => {
  let sessionService: jasmine.SpyObj<SessionService>;
  let router: jasmine.SpyObj<Router>;

  const mockRoute = {} as ActivatedRouteSnapshot;
  const mockState = { url: '/products' } as RouterStateSnapshot;

  beforeEach(() => {
    sessionService = jasmine.createSpyObj<SessionService>('SessionService', ['isAuthenticated']);
    router = jasmine.createSpyObj<Router>('Router', ['createUrlTree']);

    TestBed.configureTestingModule({
      providers: [
        { provide: SessionService, useValue: sessionService },
        { provide: Router, useValue: router },
      ],
    });
  });

  describe('guestGuard', () => {
    it('allows navigation when user is unauthenticated', () => {
      sessionService.isAuthenticated.and.returnValue(false);

      const result = TestBed.runInInjectionContext(() =>
        guestGuard(mockRoute, mockState),
      );

      expect(result).toBeTrue();
      expect(router.createUrlTree).not.toHaveBeenCalled();
    });

    it('redirects to /home when user is authenticated', () => {
      sessionService.isAuthenticated.and.returnValue(true);
      const targetTree = {} as UrlTree;
      router.createUrlTree.and.returnValue(targetTree);

      const result = TestBed.runInInjectionContext(() =>
        guestGuard(mockRoute, mockState),
      );

      expect(router.createUrlTree).toHaveBeenCalledWith(['/home']);
      expect(result).toBe(targetTree);
    });
  });

  describe('authGuard', () => {
    it('allows navigation when user is authenticated', () => {
      sessionService.isAuthenticated.and.returnValue(true);

      const result = TestBed.runInInjectionContext(() =>
        authGuard(mockRoute, mockState),
      );

      expect(result).toBeTrue();
      expect(router.createUrlTree).not.toHaveBeenCalled();
    });

    it('redirects to /auth/sign-in with returnUrl when user is unauthenticated', () => {
      sessionService.isAuthenticated.and.returnValue(false);
      const targetTree = {} as UrlTree;
      router.createUrlTree.and.returnValue(targetTree);

      const result = TestBed.runInInjectionContext(() =>
        authGuard(mockRoute, mockState),
      );

      expect(router.createUrlTree).toHaveBeenCalledWith(['/auth/sign-in'], {
        queryParams: { returnUrl: '/products' },
      });
      expect(result).toBe(targetTree);
    });
  });
});
