import { routes, rfqGuardrailsOwnerGuard } from './app.routes';

describe('application routes', () => {
  it('protects RFQ guardrail settings with the owner role guard', () => {
    const shell = routes.find((route) => route.path === '');
    const guardrailRoute = shell?.children?.find((route) => route.path === 'rfq/guardrails');
    expect(guardrailRoute).toBeDefined();
    expect(guardrailRoute?.canActivate).toEqual([rfqGuardrailsOwnerGuard]);
  });
});
