import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Browser, type Page } from '@playwright/test';

import {
  apiAsUser,
  createIsolatedWorkspace,
  createTestProduct,
  signIn,
} from './support/api';

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000/api/v1';
const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function scan(page: Page) {
  return new AxeBuilder({ page })
    .withTags(WCAG_21_AA)
    .exclude('.nav-item.disabled')
    .analyze();
}

function describeViolations(results: Awaited<ReturnType<typeof scan>>): string {
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s)`)
    .join('\n');
}

async function ensureStyles(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"][media="print"]').forEach((el) => {
      el.media = 'all';
    });
  });
}

async function switchToArabic(page: Page): Promise<void> {
  if ((await page.locator('html').getAttribute('dir')) !== 'rtl') {
    await page.click('.account-btn');
    await page.locator('button:has-text("العربية")').click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  }
  await ensureStyles(page);
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

interface StoredSession {
  cookies: {
    name: string;
    value: string;
    domain: string;
    path: string;
    expires: number;
    httpOnly: boolean;
    secure: boolean;
    sameSite: 'Strict' | 'Lax' | 'None';
  }[];
  origins: {
    origin: string;
    localStorage: { name: string; value: string }[];
  }[];
}

test.describe('POS Accessibility & RTL (015-pos-inventory-integration, T037) @a11y', () => {
  let creds: { ownerEmail: string; ownerPassword: string };
  let ownerStorage: StoredSession;
  let matchedProductId: string;

  test.beforeAll(async ({ browser }: { browser: Browser }) => {
    creds = await createIsolatedWorkspace();
    const token = await signIn(creds.ownerEmail, creds.ownerPassword);
    const matchedProduct = await createTestProduct(token, {
      tenant_name: 'Organic Whole Milk 1 Gallon',
      base_unit: 'each',
    });
    matchedProductId = matchedProduct.id;

    await completePosConnection(token);
    await apiAsUser(token, 'POST', '/pos/sync');

    const ownerCtx = await browser.newContext();
    const ownerPage = await ownerCtx.newPage();
    await ownerPage.goto('/auth/sign-in');
    await ownerPage.fill('input[formControlName="email"]', creds.ownerEmail);
    await ownerPage.fill('input[formControlName="password"]', creds.ownerPassword);
    await ownerPage.click('button[type="submit"]');
    await ownerPage.waitForURL('**/home');
    ownerStorage = await ownerCtx.storageState();
    await ownerCtx.close();
  });

  async function applySession(page: Page): Promise<void> {
    await page.context().addCookies(ownerStorage.cookies);
    for (const origin of ownerStorage.origins) {
      await page.addInitScript(
        ({ originData }) => {
          for (const item of originData.localStorage) {
            localStorage.setItem(item.name, item.value);
          }
        },
        { originData: origin },
      );
    }
    await ensureStyles(page);
  }

  test('connection settings in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await applySession(page);
    await page.goto('/pos');
    await expect(page.locator('.page-title')).toContainText('Point of Sale & Inventory Integration');
    await expect(page.locator('[data-testid="connection-status-card"]')).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('signals review in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await applySession(page);
    await page.goto('/pos/signals');
    await expect(page.locator('.page-title')).toContainText('Synced Product Signals');
    await expect(page.locator('[data-testid="matched-row"]').first()).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Smart Compare POS context in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await applySession(page);
    await page.goto(`/offers/compare?product_id=${matchedProductId}`);
    await expect(page.locator('.page-title')).toContainText('Smart Compare');
    await expect(page.locator('[data-testid="pos-inline-context"]')).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('catalogue product POS context in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await applySession(page);
    await page.goto(`/products/${matchedProductId}`);
    await expect(page.locator('.page-title')).toContainText('Edit Product');
    await expect(page.locator('[data-testid="pos-inline-context"]')).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('connection settings in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await applySession(page);
    await page.goto('/pos');
    await switchToArabic(page);
    await expect(page.locator('.page-title')).toContainText('ربط نقاط البيع والمخزون');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('signals review in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await applySession(page);
    await page.goto('/pos/signals');
    await switchToArabic(page);
    await expect(page.locator('.page-title')).toContainText('مؤشرات المنتجات المتزامنة');
    await expect(page.locator('[data-testid="matched-row"]').first()).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Smart Compare POS context in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await applySession(page);
    await page.goto(`/offers/compare?product_id=${matchedProductId}`);
    await switchToArabic(page);
    await expect(page.locator('.page-title')).toContainText('مقارنة العروض الذكية');
    await expect(page.locator('[data-testid="pos-inline-context"]')).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('catalogue product POS context in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await applySession(page);
    await page.goto(`/products/${matchedProductId}`);
    await switchToArabic(page);
    await expect(page.locator('.page-title')).toContainText('تعديل المنتج');
    await expect(page.locator('[data-testid="pos-inline-context"]')).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
