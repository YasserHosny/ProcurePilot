import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

import {
  credentials,
  type Credentials,
  signInOwner,
  apiAsUser,
  createTestProduct,
} from './support/api';

/**
 * Accessibility for Purchase Requests and Approval Queue (chunk 008, T046, FR-012, FR-013).
 *
 * WCAG 2.1 AA across the four request/approval surfaces in both English and Arabic (RTL):
 * 1. Request Creation (/requests/new)
 * 2. Request List (/requests)
 * 3. Request Detail (/requests/:id)
 * 4. Approval Queue (/approvals)
 *
 * Asserted with zero violations using request data seeded via API helpers.
 */
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

test.describe('Requests and Approvals Accessibility @a11y', () => {
  let workspace: Credentials;
  let ownerToken: string;
  let draftRequestId: string;

  test.beforeAll(async () => {
    workspace = credentials();
    ownerToken = await signInOwner();

    // 1. Seed a branch so the request form branch dropdown is populated
    const branch = await apiAsUser<{ id: string }>(
      ownerToken,
      'POST',
      '/organisation/branches',
      {
        name: `A11y Branch ${Date.now()}`,
        address: '10 Queensway',
        region: 'GB',
      },
    );

    // 2. Seed a catalogue product for line items
    const product = await createTestProduct(ownerToken, {
      tenant_name: `A11y Item ${Date.now()}`,
    });

    const futureDate = new Date(Date.now() + 30 * 86_400_000).toISOString().split('T')[0]!;

    // 3. Seed a draft request for the detail screen
    const draft = await apiAsUser<{ id: string }>(ownerToken, 'POST', '/requests', {
      branch_id: branch.id,
      required_by_date: futureDate,
      lines: [{ workspace_product_id: product.id, quantity: '5' }],
    });
    draftRequestId = draft.id;

    // 4. Seed and submit a request so the approval queue has a real pending item
    const submitted = await apiAsUser<{ id: string }>(ownerToken, 'POST', '/requests', {
      branch_id: branch.id,
      required_by_date: futureDate,
      lines: [{ workspace_product_id: product.id, quantity: '10' }],
    });
    await apiAsUser(ownerToken, 'POST', `/requests/${submitted.id}/submit`);
  });

  async function signInUser(page: Page) {
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', workspace.ownerEmail);
    await page.fill('input[formControlName="password"]', workspace.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  }

  async function ensureEnglish(page: Page) {
    if ((await page.locator('html').getAttribute('dir')) === 'rtl') {
      await page.click('.account-btn');
      await page.locator('button[mat-menu-item]', { hasText: 'English' }).click();
      await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
    }
  }

  async function switchToArabic(page: Page) {
    if ((await page.locator('html').getAttribute('dir')) !== 'rtl') {
      await page.click('.account-btn');
      await page.locator('button[mat-menu-item]', { hasText: 'العربية' }).click();
      await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    }
  }

  // --- English WCAG 2.1 AA Scans ---

  test('the request creation screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/requests/new');
    await expect(page.locator('.form-title')).toContainText('New Purchase Request');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the request list screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/requests');
    await expect(page.locator('.section-title')).toContainText('Purchase Requests');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the request detail screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto(`/requests/${draftRequestId}`);
    await expect(page.locator('.form-title')).toContainText('Edit Purchase Request');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the approval queue screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/approvals');
    await expect(page.locator('.approval-queue-title')).toContainText('Approval Queue');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // --- Arabic (RTL) WCAG 2.1 AA Scans ---
  // Declared after English scans so persisted locale changes do not affect earlier tests.

  test('the request creation screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/requests/new');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.form-title')).toContainText('طلب شراء جديد');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the request list screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/requests');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.section-title')).toContainText('طلبات الشراء');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the request detail screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto(`/requests/${draftRequestId}`);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.form-title')).toContainText('تعديل طلب الشراء');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the approval queue screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/approvals');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.approval-queue-title')).toContainText('قائمة الاعتماد');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
