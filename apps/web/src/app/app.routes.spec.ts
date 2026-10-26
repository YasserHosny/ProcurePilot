import { routes, rfqGuardrailsOwnerGuard } from './app.routes';
import { guestGuard } from './core/auth/auth.guard';

describe('application routes', () => {
  it('protects RFQ guardrail settings with the owner role guard', () => {
    const shell = routes.find((route) => route.path === '' && !!route.children);
    const guardrailRoute = shell?.children?.find((route) => route.path === 'rfq/guardrails');
    expect(guardrailRoute).toBeDefined();
    expect(guardrailRoute?.canActivate).toEqual([rfqGuardrailsOwnerGuard]);
  });

  it('routes root path to the guest-guarded landing page', () => {
    const landingRoute = routes.find((route) => route.path === '' && route.pathMatch === 'full');
    expect(landingRoute).toBeDefined();
    expect(landingRoute?.canActivate).toEqual([guestGuard]);
  });

  it('exposes public unauthenticated legal routes for privacy and terms without guards', () => {
    const privacyRoute = routes.find((route) => route.path === 'privacy');
    expect(privacyRoute).toBeDefined();
    expect(privacyRoute?.canActivate).toBeUndefined();
    expect(privacyRoute?.loadComponent).toBeDefined();

    const termsRoute = routes.find((route) => route.path === 'terms');
    expect(termsRoute).toBeDefined();
    expect(termsRoute?.canActivate).toBeUndefined();
    expect(termsRoute?.loadComponent).toBeDefined();
  });
});
