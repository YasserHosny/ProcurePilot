import { test, expect, type Page } from '@playwright/test';

import {
  apiAsUser,
  createIsolatedWorkspace,
  createTestProduct,
  signIn,
} from './support/api';

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000/api/v1';

async function ensureEnglish(page: Page): Promise<void> {
  if ((await page.locator('html').getAttribute('dir')) === 'rtl') {
    await page.click('.account-btn');
    await page.locator('button[mat-menu-item]', { hasText: 'English' }).click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
  }
}

async function signInUi(page: Page, email: string, password: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto('/auth/sign-in');
  await page.evaluate(() => localStorage.clear());
  await page.fill('input[formControlName="email"]', email);
  await page.fill('input[formControlName="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
  await ensureEnglish(page);
}

async function completePosConnection(token: string): Promise<void> {
  const start = await apiAsUser<{ authorization_url: string }>(token, 'POST', '/pos/connect');
  const url = new URL(start.authorization_url);
  const state = url.searchParams.get('state');
  if (!state) {
    throw new Error('POS authorization URL did not include state');
  }

  const callback = await fetch(
    `${API}/pos/connect/callback?code=stub-auth-code&state=${encodeURIComponent(state)}`,
    { redirect: 'manual' },
  );
  expect(callback.status).toBe(302);
}

test.describe('POS & Inventory Integration (015-pos-inventory-integration, T036)', () => {
  test('connects, syncs, shows usage signals, manually matches, and degrades after disconnect', async ({
    page,
  }) => {
    const creds = await createIsolatedWorkspace();
    const token = await signIn(creds.ownerEmail, creds.ownerPassword);
    const matchedProduct = await createTestProduct(token, {
      tenant_name: 'Organic Whole Milk 1 Gallon',
      base_unit: 'each',
    });
    const manualTarget = await createTestProduct(token, {
      tenant_name: `Manual POS Target ${Date.now()}`,
      base_unit: 'each',
    });

    await signInUi(page, creds.ownerEmail, creds.ownerPassword);
    await page.goto('/pos');
    await expect(page.locator('.page-title')).toContainText('Point of Sale & Inventory Integration');
    await expect(page.locator('[data-testid="empty-connection-card"]')).toBeVisible();

    await page.route('**/oauth2/authorize**', async (route) => {
      const url = new URL(route.request().url());
      const state = url.searchParams.get('state') ?? '';
      const callbackUrl = `${API}/pos/connect/callback?code=stub-auth-code&state=${encodeURIComponent(state)}`;
      await route.fulfill({
        status: 302,
        headers: { Location: callbackUrl },
      });
    });

    const connectStart = Date.now();
    await page.locator('[data-testid="connect-btn"]').click();
    const statusCard = page.locator('[data-testid="connection-status-card"]');
    await expect(statusCard).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="connection-status-badge"]')).toContainText('Active');
    await expect(page.locator('[data-testid="connection-display-name"]')).toContainText(
      'ProcurePilot Demo POS Store',
    );
    expect(Date.now() - connectStart).toBeLessThan(60_000);

    await page.locator('[data-testid="view-signals-btn"]').click();
    await page.waitForURL('**/pos/signals');
    await expect(page.locator('.page-title')).toContainText('POS Usage Signals');

    const syncResponse = page.waitForResponse(
      (res) => res.url().includes('/pos/sync') && res.request().method() === 'POST',
    );
    await page.locator('[data-testid="sync-btn"]').click();
    expect((await syncResponse).status()).toBe(202);

    const matchedRows = page.locator('[data-testid="matched-row"]');
    await expect(matchedRows.first()).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="matched-section"]')).toContainText(
      'Organic Whole Milk 1 Gallon',
    );
    await expect(page.locator('[data-testid="matched-section"]')).toContainText('45.0000');
    await expect(page.locator('[data-testid="matched-section"]')).toContainText('0.8000');

    await expect(page.locator('[data-testid="unmatched-row"]').first()).toBeVisible();
    const firstUnmatched = page.locator('[data-testid="unmatched-row"]').first();
    await firstUnmatched.locator('[data-testid="product-picker"]').click();
    await page.locator('mat-option', { hasText: manualTarget.tenant_name }).click();

    const matchResponse = page.waitForResponse(
      (res) => res.url().includes('/pos/signals/') && res.url().endsWith('/match'),
    );
    await firstUnmatched.locator('[data-testid="match-btn"]').click();
    expect((await matchResponse).status()).toBe(200);
    await expect(page.locator('[data-testid="matched-section"]')).toContainText(
      manualTarget.tenant_name,
    );

    await page.goto(`/offers/compare?product_id=${matchedProduct.id}`);
    await expect(page.locator('.page-title')).toContainText('Smart Compare');
    await expect(page.locator('[data-testid="pos-inline-context"]')).toBeVisible();
    await expect(page.locator('[data-testid="pos-stock-on-hand"]')).toContainText('45.0000');
    await expect(page.locator('[data-testid="pos-sales-velocity"]')).toContainText('0.8000');

    await page.goto(`/products/${matchedProduct.id}`);
    await expect(page.locator('.page-title')).toContainText('Edit Product');
    await expect(page.locator('[data-testid="pos-inline-context"]')).toBeVisible();

    await page.goto('/pos');
    await page.locator('[data-testid="disconnect-btn"]').click();
    await expect(page.locator('[data-testid="connection-status-badge"]')).toContainText(
      'Disconnected',
    );

    await page.goto('/offers/compare');
    await expect(page.locator('.page-title')).toContainText('Smart Compare');
    await expect(page.locator('.controls-card')).toBeVisible();

    await page.goto('/products');
    await expect(page.locator('.page-title')).toContainText('Product Master');
    await expect(page.locator('tr[mat-row]', { hasText: matchedProduct.tenant_name })).toBeVisible();
  });

  test('manual setup helper can connect through the backend stub flow', async () => {
    const creds = await createIsolatedWorkspace();
    const token = await signIn(creds.ownerEmail, creds.ownerPassword);

    await completePosConnection(token);
    const connection = await apiAsUser<{ status: string; display_name: string }>(
      token,
      'GET',
      '/pos/connection',
    );

    expect(connection.status).toBe('active');
    expect(connection.display_name).toBe('ProcurePilot Demo POS Store');
  });
});
