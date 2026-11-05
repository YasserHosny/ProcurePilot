import AxeBuilder from '@axe-core/playwright';
import { test, expect, type BrowserContext, type Page } from '@playwright/test';

import {
  apiAsUser,
  createIsolatedWorkspace,
  createTestOrder,
  createTestProduct,
  createTestSupplier,
  setOwnerLocale,
  signIn,
  type Credentials,
} from './support/api';

/**
 * Accessibility and RTL for the purchase-order and basket-split screens (PPS-211, P-187).
 *
 * WCAG 2.1 AA in English and in Arabic (RTL) on the order list, the create form, the order
 * detail page (draft, and sent with its inline forms and confirmations open) and the basket
 * split form. One isolated workspace, one sign-in, so the auth rate limit stays out of the way.
 */
const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const BASE_URL = process.env['E2E_BASE_URL'] ?? 'http://localhost:4200';

async function scan(page: Page) {
  return new AxeBuilder({ page }).withTags(WCAG_21_AA).exclude('.nav-item.disabled').analyze();
}

function describeViolations(results: Awaited<ReturnType<typeof scan>>): string {
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s): ${v.nodes
      .slice(0, 3)
      .map((n) => n.target.join(' '))
      .join(' | ')}`)
    .join('\n');
}

test.describe.configure({ mode: 'serial' });

test.describe('Orders and basket split accessibility @a11y', () => {
  let context: BrowserContext;
  let page: Page;
  let credentials: Credentials;
  let token: string;
  let draftOrderId: string;
  let sentOrderId: string;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(300_000);
    credentials = await createIsolatedWorkspace();
    token = await signIn(credentials.ownerEmail, credentials.ownerPassword);
    const first = await createTestSupplier(token, `A11y Supplier A ${Date.now()}`);
    await createTestSupplier(token, `A11y Supplier B ${Date.now()}`);
    const product = await createTestProduct(token, { tenant_name: `A11y Paper ${Date.now()}` });
    draftOrderId = (await createTestOrder(token, { supplier_id: first.id, product_id: product.id })).id;
    const sent = await createTestOrder(token, { supplier_id: first.id, product_id: product.id });
    sentOrderId = sent.id;
    await apiAsUser(token, 'POST', `/orders/${sentOrderId}/submit`, undefined, {
      'Idempotency-Key': crypto.randomUUID(),
    });

    context = await browser.newContext({ baseURL: BASE_URL });
    page = await context.newPage();
    await page.goto('/auth/sign-in');
    await page.evaluate(() => localStorage.clear());
    await page.fill('input[formControlName="email"]', credentials.ownerEmail);
    await page.fill('input[formControlName="password"]', credentials.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test.afterAll(async () => {
    await context?.close();
  });

  async function openAndScan(url: string, ready: string, dir: 'ltr' | 'rtl'): Promise<void> {
    await page.goto(url);
    await expect(page.locator('html')).toHaveAttribute('dir', dir);
    await expect(page.locator(ready).first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  }

  function suite(label: string, dir: 'ltr' | 'rtl'): void {
    test(`the order list in ${label} has no WCAG 2.1 AA violations @a11y`, async () => {
      await openAndScan('/orders', '[data-testid="orders-list"]', dir);
    });

    test(`the create order form in ${label} has no WCAG 2.1 AA violations @a11y`, async () => {
      await openAndScan('/orders/new', 'form', dir);
    });

    test(`a draft order in ${label} with its confirmations open has no violations @a11y`, async () => {
      await openAndScan(`/orders/${draftOrderId}`, '[data-testid="order-lines"]', dir);
      await page.locator('[data-testid="submit-order"]').click();
      await expect(page.locator('[data-testid="submit-confirm-panel"]')).toBeVisible();
      let results = await scan(page);
      expect(results.violations, describeViolations(results)).toEqual([]);
      await page.locator('[data-testid="cancel-order"]').click();
      await expect(page.locator('[data-testid="cancel-confirm-panel"]')).toBeVisible();
      results = await scan(page);
      expect(results.violations, describeViolations(results)).toEqual([]);
    });

    test(`a sent order in ${label} with the receipt form open has no violations @a11y`, async () => {
      await openAndScan(`/orders/${sentOrderId}`, '[data-testid="order-lines"]', dir);
      await page.locator('[data-testid="withdraw-order"]').click();
      await expect(page.locator('[data-testid="withdraw-confirm-panel"]')).toBeVisible();
      let results = await scan(page);
      expect(results.violations, describeViolations(results)).toEqual([]);
      await page.locator('[data-testid="open-receipt-form"]').click();
      await expect(page.locator('[data-testid="save-receipt"]')).toBeVisible();
      results = await scan(page);
      expect(results.violations, describeViolations(results)).toEqual([]);
    });

    test(`the basket split form in ${label} has no WCAG 2.1 AA violations @a11y`, async () => {
      await openAndScan('/offers/basket-split', 'form', dir);
    });
  }

  suite('English', 'ltr');

  test('switch the workspace to Arabic', async () => {
    await setOwnerLocale('ar', token);
    await page.goto('/home');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  });

  suite('Arabic (RTL)', 'rtl');

  test.afterAll(async () => {
    if (token) await setOwnerLocale('en', token);
  });
});
