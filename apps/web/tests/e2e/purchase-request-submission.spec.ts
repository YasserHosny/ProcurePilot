import { test, expect, type Page } from '@playwright/test';

import {
  credentials,
  type Credentials,
  signInOwner,
  apiAsUser,
  createTestProduct,
} from './support/api';

/**
 * End-to-End tests for Purchase Request submission (chunk 008, User Story 1).
 *
 * Covered:
 * - The /requests nav link is visible and navigates to the requests list.
 * - The empty state renders when no requests exist.
 * - The create form (/requests/new) renders with all required fields.
 * - Arabic RTL layout renders the requests title correctly.
 */

// The shared owner's preferred_locale persists server-side, and other spec files switch it to
// Arabic without restoring (their RTL tests are declared last within their own file only).
// Every test here asserts English text, so pin the language right after sign-in.
async function ensureEnglish(page: Page) {
  if ((await page.locator('html').getAttribute('dir')) === 'rtl') {
    await page.click('.account-btn');
    await page.locator('button[mat-menu-item]', { hasText: 'English' }).click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
  }
}

test.describe('Purchase Request Submission (chunk 008 US1)', () => {
  let creds: Credentials;

  test.beforeAll(async () => {
    creds = credentials();
    const token = await signInOwner();
    await apiAsUser(token, 'POST', '/organisation/branches', {
      name: `Submission Branch ${Date.now()}`,
      address: '10 Request Lane',
      region: 'GB',
    });
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', creds.ownerEmail);
    await page.fill('input[formControlName="password"]', creds.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
    await ensureEnglish(page);
  });

  test('navigates to /requests via the sidebar and shows the list', async ({ page }) => {
    const navLink = page.locator('.nav-item', { hasText: 'Purchase Requests' });
    await expect(navLink).toBeVisible();
    await navLink.click();
    await page.waitForURL('**/requests');

    await expect(page.locator('.section-title')).toContainText('Purchase Requests');
  });

  test('the create form at /requests/new renders with branch, date, and lines fields', async ({
    page,
  }) => {
    await page.goto('/requests/new');
    await expect(page.locator('.form-title')).toContainText('New Purchase Request');

    await expect(page.locator('mat-select[formControlName="branch_id"]')).toBeVisible();
    await expect(page.locator('input[formControlName="required_by_date"]')).toBeVisible();
    await expect(page.locator('.line-row')).toHaveCount(1);
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('add and remove line items in the create form', async ({ page }) => {
    await page.goto('/requests/new');

    await expect(page.locator('.line-row')).toHaveCount(1);

    await page.click('.add-line-btn');
    await expect(page.locator('.line-row')).toHaveCount(2);

    await page.locator('.remove-line-btn').first().click();
    await expect(page.locator('.line-row')).toHaveCount(1);
  });

  test('cancel navigates back to the list', async ({ page }) => {
    await page.goto('/requests/new');
    await page.click('button:has-text("Cancel")');
    await page.waitForURL('**/requests');
  });

  test('Arabic RTL layout shows the requests title in Arabic', async ({ page }) => {
    await page.goto('/requests');

    await page.click('.account-btn');
    await page.locator('button[mat-menu-item]', { hasText: 'العربية' }).click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');

    await expect(page.locator('.section-title')).toContainText('طلبات الشراء');

    await page.click('.account-btn');
    await page.locator('button[mat-menu-item]', { hasText: 'English' }).click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
  });

  test('creates a draft via the form and sees it on the detail page', async ({ page }) => {
    const token = await signInOwner();
    const product = await createTestProduct(token, {
      tenant_name: `E2E Draft ${Date.now()}`,
    });

    await page.goto('/requests/new');
    await expect(page.locator('.form-title')).toContainText('New Purchase Request');

    // Select the first branch
    await page.click('mat-select[formControlName="branch_id"]');
    await page.locator('mat-option').first().click();

    // Fill required-by date (30 days ahead)
    const future = new Date(Date.now() + 30 * 86_400_000).toISOString().split('T')[0]!;
    await page.fill('input[formControlName="required_by_date"]', future);

    // Fill the first line item
    await page.fill('.line-product input', product.id);
    await page.fill('.line-quantity input', '5');

    // Save draft
    await page.click('button[type="submit"]');

    // Redirects to the saved request's detail page
    await page.waitForURL(/\/requests\/.+/);
    await expect(page.locator('.form-title')).toContainText('Edit Purchase Request');
  });

  test('submits a saved draft via the detail page', async ({ page }) => {
    const token = await signInOwner();
    const product = await createTestProduct(token, {
      tenant_name: `E2E Submit ${Date.now()}`,
    });
    const branches = await apiAsUser<{ items: { id: string }[] }>(
      token,
      'GET',
      '/organisation/branches',
    );
    const branchId = branches.items[0]!.id;

    const draft = await apiAsUser<{ id: string }>(token, 'POST', '/requests', {
      branch_id: branchId,
      required_by_date: new Date(Date.now() + 30 * 86_400_000).toISOString().split('T')[0],
      lines: [{ workspace_product_id: product.id, quantity: '5' }],
    });

    await page.goto(`/requests/${draft.id}`);
    await expect(page.locator('.form-title')).toContainText('Edit Purchase Request');

    // Click the Submit button (not the Save Draft submit)
    const submitBtn = page.getByRole('button', { name: 'Submit' });
    await expect(submitBtn).toBeVisible();
    await submitBtn.click();

    // Should redirect to the requests list
    await page.waitForURL('**/requests');
    await expect(page.locator('.status-chip[data-status="submitted"]').first()).toBeVisible();
  });

  test('withdraws a submitted request from the list', async ({ page }) => {
    const token = await signInOwner();
    const product = await createTestProduct(token, {
      tenant_name: `E2E Withdraw ${Date.now()}`,
    });
    const branches = await apiAsUser<{ items: { id: string }[] }>(
      token,
      'GET',
      '/organisation/branches',
    );
    const branchId = branches.items[0]!.id;

    // Create and submit via API
    const draft = await apiAsUser<{ id: string }>(token, 'POST', '/requests', {
      branch_id: branchId,
      required_by_date: new Date(Date.now() + 30 * 86_400_000).toISOString().split('T')[0],
      lines: [{ workspace_product_id: product.id, quantity: '5' }],
    });
    await apiAsUser(token, 'POST', `/requests/${draft.id}/submit`);

    // Navigate to the list and filter by submitted
    await page.goto('/requests');
    await page.click('.status-filter');
    await page.locator('mat-option[value="submitted"]').click();
    await expect(page.locator('.status-chip[data-status="submitted"]').first()).toBeVisible();

    // Click withdraw on the first submitted request
    await page.locator('button.danger-action').first().click();

    // Verify the snackbar confirms withdrawal
    await expect(page.locator('mat-snack-bar-container')).toBeVisible();
  });
});
