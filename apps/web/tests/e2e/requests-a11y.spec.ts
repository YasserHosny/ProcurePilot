import { randomUUID } from 'node:crypto';
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
 * Accessibility for Purchase Requests and Approvals (chunk 008, T046, FR-012, FR-013).
 *
 * WCAG 2.1 AA across the request/approval surfaces in both English and Arabic (RTL):
 * 1. Request Creation (/requests/new)
 * 2. Request List (/requests)
 * 3. Request Detail (/requests/:id)
 * 4. Approval Queue (/approvals)
 * 5. Approval Detail (/approvals/:requestId)
 * 6. Bulk selection bar, approve confirmation, and reject dialog (empty/filled comment)
 * 7. Bulk decision results (P-177, PPS-171; separate request per locale)
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
  let submittedRequestId: string;
  let englishBulkRequestId: string;
  let arabicBulkRequestId: string;
  let branchId: string;
  let productId: string;
  const requestIds: string[] = [];

  test.beforeAll(async () => {
    workspace = credentials();
    ownerToken = await signInOwner();

    const marker = `a11y-${randomUUID()}`;

    // 1. Seed a branch so the request form branch dropdown is populated
    const branch = await apiAsUser<{ id: string }>(
      ownerToken,
      'POST',
      '/organisation/branches',
      {
        name: marker,
        address: '10 Queensway',
        region: 'GB',
      },
    );

    // 2. Seed a catalogue product for line items
    const product = await createTestProduct(ownerToken, {
      tenant_name: marker,
    });

    branchId = branch.id;
    productId = product.id;

    const futureDate = new Date(Date.now() + 30 * 86_400_000).toISOString().split('T')[0]!;

    // 3. Seed a draft request for the detail screen
    const draft = await apiAsUser<{ id: string }>(ownerToken, 'POST', '/requests', {
      branch_id: branch.id,
      required_by_date: futureDate,
      lines: [{ workspace_product_id: product.id, quantity: '5', note: `${marker}-draft` }],
    });
    draftRequestId = draft.id;
    requestIds.push(draft.id);

    // 4. Seed and submit a request so the approval queue has a real pending item
    const submitted = await apiAsUser<{ id: string }>(ownerToken, 'POST', '/requests', {
      branch_id: branch.id,
      required_by_date: futureDate,
      lines: [{ workspace_product_id: product.id, quantity: '10', note: `${marker}-submitted` }],
    });
    submittedRequestId = submitted.id;
    requestIds.push(submitted.id);
    await apiAsUser(ownerToken, 'POST', `/requests/${submitted.id}/submit`);

    // Each locale consumes its own request; the original stays pending for non-decision scans.
    for (const locale of ['en', 'ar']) {
      const bulkRequest = await apiAsUser<{ id: string }>(ownerToken, 'POST', '/requests', {
        branch_id: branch.id,
        required_by_date: futureDate,
        lines: [{ workspace_product_id: product.id, quantity: '10', note: `${marker}-bulk-${locale}` }],
      });
      requestIds.push(bulkRequest.id);
      await apiAsUser(ownerToken, 'POST', `/requests/${bulkRequest.id}/submit`);
      if (locale === 'en') englishBulkRequestId = bulkRequest.id;
      else arabicBulkRequestId = bulkRequest.id;
    }
  });

  test.afterAll(async () => {
    for (const id of requestIds) {
      const request = await apiAsUser<{ status: string }>(ownerToken, 'GET', `/requests/${id}`);
      if (request.status === 'draft' || request.status === 'submitted') {
        await apiAsUser(ownerToken, 'POST', `/requests/${id}/withdraw`);
      }
    }
    if (productId) await apiAsUser(ownerToken, 'DELETE', `/products/${productId}`);
    if (branchId) await apiAsUser(ownerToken, 'PATCH', `/organisation/branches/${branchId}`, {
      is_active: false, confirm_dependents: true,
    });
  });

  test.afterEach(async ({ page }) => {
    await ensureEnglish(page);
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

  test('the approval detail screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto(`/approvals/${submittedRequestId}`);
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('h1')).toContainText('Request');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('invalid request submission in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/requests/new');
    await page.getByRole('button', { name: 'Save Draft', exact: true }).click();
    await expect(page.locator('.error-banner[role="alert"]')).toBeVisible();
    for (const [label, message] of [['Branch', 'Branch is required'], ['Required By', 'Required-by date is required'], ['Product', 'Select a product'], ['Quantity', 'Quantity must be greater than zero']]) {
      await expect(page.getByLabel(label!, { exact: true })).toHaveAccessibleDescription(new RegExp(message!));
    }
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the bulk bar in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/approvals');
    await expect(page.locator('.approval-queue-title')).toContainText('Approval Queue');
    await page.waitForLoadState('networkidle');
    const row = page.locator('tr.request-row').filter({
      has: page.locator(`a[href="/approvals/${submittedRequestId}"]`),
    });
    await row.getByRole('checkbox').check();
    const bulkBar = page.getByRole('region', { name: 'Bulk decisions', exact: true });
    await expect(bulkBar).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the bulk approve confirm dialog in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/approvals');
    await expect(page.locator('.approval-queue-title')).toContainText('Approval Queue');
    await page.waitForLoadState('networkidle');
    const row = page.locator('tr.request-row').filter({
      has: page.locator(`a[href="/approvals/${submittedRequestId}"]`),
    });
    await row.getByRole('checkbox').check();
    const bulkBar = page.getByRole('region', { name: 'Bulk decisions', exact: true });
    await expect(bulkBar).toBeVisible();
    await bulkBar.getByRole('button', { name: 'Approve', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Approve 1 request?', exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading', { name: 'Approve 1 request?', exact: true })).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).not.toBeVisible();
  });

  test('the bulk reject dialog in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/approvals');
    await expect(page.locator('.approval-queue-title')).toContainText('Approval Queue');
    await page.waitForLoadState('networkidle');
    const row = page.locator('tr.request-row').filter({
      has: page.locator(`a[href="/approvals/${submittedRequestId}"]`),
    });
    await row.getByRole('checkbox').check();
    const bulkBar = page.getByRole('region', { name: 'Bulk decisions', exact: true });
    await expect(bulkBar).toBeVisible();
    await bulkBar.getByRole('button', { name: 'Reject', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Reject 1 request?', exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading', { name: 'Reject 1 request?', exact: true })).toBeVisible();
    await expect(dialog.getByRole('textbox', { name: 'Rejection reason' })).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
    await dialog.getByRole('textbox', { name: 'Rejection reason' }).fill('Accessibility coverage');
    const filledResults = await scan(page);
    expect(filledResults.violations, describeViolations(filledResults)).toEqual([]);
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).not.toBeVisible();
  });

  test('the bulk results panel in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/approvals');
    await expect(page.locator('.approval-queue-title')).toContainText('Approval Queue');
    await page.waitForLoadState('networkidle');
    const row = page.locator('tr.request-row').filter({
      has: page.locator(`a[href="/approvals/${englishBulkRequestId}"]`),
    });
    await row.getByRole('checkbox').check();
    const bulkBar = page.getByRole('region', { name: 'Bulk decisions', exact: true });
    await expect(bulkBar).toBeVisible();
    await bulkBar.getByRole('button', { name: 'Approve', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Approve 1 request?', exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading', { name: 'Approve 1 request?', exact: true })).toBeVisible();
    await dialog.getByRole('button', { name: 'Approve', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByTestId('bulk-results')).toBeVisible();
    await expect(page.getByRole('region', { name: 'Decision results', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Decision results', exact: true })).toBeVisible();
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

  test('the approval detail screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto(`/approvals/${submittedRequestId}`);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('h1')).toContainText('الطلب');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('invalid request submission in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/requests/new');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await page.getByRole('button', { name: 'حفظ كمسودة', exact: true }).click();
    await expect(page.locator('.error-banner[role="alert"]')).toBeVisible();
    for (const [label, message] of [['الفرع', 'الفرع مطلوب'], ['مطلوب بحلول', 'تاريخ الاستحقاق مطلوب'], ['المنتج', 'اختر منتجًا'], ['الكمية', 'يجب أن تكون الكمية أكبر من صفر']]) {
      await expect(page.getByLabel(label!, { exact: true })).toHaveAccessibleDescription(new RegExp(message!));
    }
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the bulk bar in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/approvals');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.approval-queue-title')).toContainText('قائمة الاعتماد');
    await page.waitForLoadState('networkidle');
    const row = page.locator('tr.request-row').filter({
      has: page.locator(`a[href="/approvals/${submittedRequestId}"]`),
    });
    await row.getByRole('checkbox').check();
    const bulkBar = page.getByRole('region', { name: 'قرارات مجمعة', exact: true });
    await expect(bulkBar).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the bulk approve confirm dialog in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/approvals');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.approval-queue-title')).toContainText('قائمة الاعتماد');
    await page.waitForLoadState('networkidle');
    const row = page.locator('tr.request-row').filter({
      has: page.locator(`a[href="/approvals/${submittedRequestId}"]`),
    });
    await row.getByRole('checkbox').check();
    const bulkBar = page.getByRole('region', { name: 'قرارات مجمعة', exact: true });
    await expect(bulkBar).toBeVisible();
    await bulkBar.getByRole('button', { name: 'موافقة', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'الموافقة على طلب واحد؟', exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading', { name: 'الموافقة على طلب واحد؟', exact: true })).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
    await dialog.getByRole('button', { name: 'إلغاء', exact: true }).click();
    await expect(dialog).not.toBeVisible();
  });

  test('the bulk reject dialog in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/approvals');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.approval-queue-title')).toContainText('قائمة الاعتماد');
    await page.waitForLoadState('networkidle');
    const row = page.locator('tr.request-row').filter({
      has: page.locator(`a[href="/approvals/${submittedRequestId}"]`),
    });
    await row.getByRole('checkbox').check();
    const bulkBar = page.getByRole('region', { name: 'قرارات مجمعة', exact: true });
    await expect(bulkBar).toBeVisible();
    await bulkBar.getByRole('button', { name: 'رفض', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'رفض طلب واحد؟', exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading', { name: 'رفض طلب واحد؟', exact: true })).toBeVisible();
    await expect(dialog.getByRole('textbox', { name: 'سبب الرفض' })).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
    await dialog.getByRole('textbox', { name: 'سبب الرفض' }).fill('Accessibility coverage');
    const filledResults = await scan(page);
    expect(filledResults.violations, describeViolations(filledResults)).toEqual([]);
    await dialog.getByRole('button', { name: 'إلغاء', exact: true }).click();
    await expect(dialog).not.toBeVisible();
  });

  test('the bulk results panel in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/approvals');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.approval-queue-title')).toContainText('قائمة الاعتماد');
    await page.waitForLoadState('networkidle');
    const row = page.locator('tr.request-row').filter({
      has: page.locator(`a[href="/approvals/${arabicBulkRequestId}"]`),
    });
    await row.getByRole('checkbox').check();
    const bulkBar = page.getByRole('region', { name: 'قرارات مجمعة', exact: true });
    await expect(bulkBar).toBeVisible();
    await bulkBar.getByRole('button', { name: 'موافقة', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'الموافقة على طلب واحد؟', exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading', { name: 'الموافقة على طلب واحد؟', exact: true })).toBeVisible();
    await dialog.getByRole('button', { name: 'موافقة', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByTestId('bulk-results')).toBeVisible();
    await expect(page.getByRole('region', { name: 'نتائج القرارات', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'نتائج القرارات', exact: true })).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

});
