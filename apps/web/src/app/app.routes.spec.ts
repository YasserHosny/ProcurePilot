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
});
