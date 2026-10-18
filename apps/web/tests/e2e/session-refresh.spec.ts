import { Page, expect, test } from '@playwright/test';

import { createIsolatedWorkspace } from './support/api';

/**
 * Session renewal, end to end against the real API and Supabase Auth — demo finding 29.
 *
 * The Supabase access token lasts an hour and nothing used to renew it, so everyone was signed
 * out hourly. Waiting an hour is not a test, so these specs make the stored access token unusable
 * instead: the payload's `exp` is rewritten, which also breaks the signature, so the server
 * refuses it exactly as it refuses an expired one. The refresh token stays real, and the renewed
 * session must come from the real /auth/refresh and still carry the original workspace's claim.
 */

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000/api/v1';

interface RealSession {
  access_token: string;
  refresh_token: string;
}

function claims(token: string): { exp: number; tenant_id?: string } {
  const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
  return JSON.parse(Buffer.from(payload, 'base64').toString('utf-8'));
}

/** The real token with `exp` moved — so its signature no longer verifies. */
function withExp(token: string, expSeconds: number): string {
  const [header, , signature] = token.split('.');
  const payload = Buffer.from(JSON.stringify({ ...claims(token), exp: expSeconds }))
    .toString('base64url');
  return `${header}.${payload}.${signature}`;
}

async function signInForSession(email: string, password: string): Promise<RealSession> {
  const response = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  expect(response.ok).toBeTruthy();
  return (await response.json()) as RealSession;
}

async function seedStorage(page: Page, access: string, refresh: string): Promise<void> {
  await page.addInitScript(
    ([a, r]) => {
      // Only on the first document: a later reload must see what the app itself stored.
      if (sessionStorage.getItem('pp.e2e.seeded')) return;
      sessionStorage.setItem('pp.e2e.seeded', '1');
      localStorage.setItem('pp.access_token', a);
      localStorage.setItem('pp.refresh_token', r);
    },
    [access, refresh],
  );
}

test.describe('Session refresh (demo finding 29)', () => {
  let email: string;
  let password: string;

  test.beforeAll(async () => {
    const creds = await createIsolatedWorkspace();
    email = creds.ownerEmail;
    password = creds.ownerPassword;
  });

  test('an expired stored token is renewed on start instead of bouncing to sign-in', async ({
    page,
  }) => {
    const real = await signInForSession(email, password);
    const tenant = claims(real.access_token).tenant_id;
    expect(tenant).toBeTruthy();

    const refreshCalls: string[] = [];
    page.on('request', (r) => {
      if (r.url().endsWith('/api/v1/auth/refresh')) refreshCalls.push(r.method());
    });

    const expired = withExp(real.access_token, Math.floor(Date.now() / 1000) - 60);
    await seedStorage(page, expired, real.refresh_token);
    const renewed = page.waitForResponse((r) => r.url().endsWith('/api/v1/auth/refresh'));
    await page.goto('/requests');
    expect((await renewed).status()).toBe(200);

    // The URL reads /requests before the initializer settles, so wait for the page itself.
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    expect(page.url()).toContain('/requests');
    expect(refreshCalls).toEqual(['POST']);

    const stored = await page.evaluate(() => ({
      access: localStorage.getItem('pp.access_token'),
      refresh: localStorage.getItem('pp.refresh_token'),
    }));
    expect(stored.access).not.toBe(expired);
    expect(stored.refresh).not.toBe(real.refresh_token); // Supabase rotates it on use.
    expect(claims(stored.access ?? '').tenant_id).toBe(tenant);
    expect(claims(stored.access ?? '').exp * 1000).toBeGreaterThan(Date.now());
  });

  test('a token the server refuses mid-session is renewed once and the request replayed', async ({
    page,
  }) => {
    const real = await signInForSession(email, password);
    const tenant = claims(real.access_token).tenant_id;

    // exp in the future, so the client sees no reason to refresh — only the server's 401 does.
    const refused = withExp(real.access_token, Math.floor(Date.now() / 1000) + 1800);
    const refreshCalls: string[] = [];
    const unauthorised: string[] = [];
    page.on('request', (r) => {
      if (r.url().endsWith('/api/v1/auth/refresh')) refreshCalls.push(r.method());
    });
    page.on('response', (r) => {
      if (r.status() === 401 && r.url().includes('/api/v1/')) unauthorised.push(r.url());
    });

    await seedStorage(page, refused, real.refresh_token);
    const renewed = page.waitForResponse((r) => r.url().endsWith('/api/v1/auth/refresh'));
    await page.goto('/requests');
    expect((await renewed).status()).toBe(200);

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    expect(page.url()).toContain('/requests');
    expect(unauthorised.length).toBeGreaterThan(0);
    expect(refreshCalls).toEqual(['POST']);

    const access = await page.evaluate(() => localStorage.getItem('pp.access_token'));
    expect(access).not.toBe(refused);
    expect(claims(access ?? '').tenant_id).toBe(tenant);
  });

  test('a spent refresh token signs the person out as before', async ({ page }) => {
    const real = await signInForSession(email, password);
    const expired = withExp(real.access_token, Math.floor(Date.now() / 1000) - 60);

    await seedStorage(page, expired, 'not-a-real-refresh-token');
    await page.goto('/requests');

    await expect(page).toHaveURL(/\/auth\/sign-in/);
    const stored = await page.evaluate(() => localStorage.getItem('pp.refresh_token'));
    expect(stored).toBeNull();
  });
});
