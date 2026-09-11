import { test, expect, type Page } from '@playwright/test';

import {
  apiAsUser,
  createMember,
  createTestProduct,
  credentials,
  signIn,
  signInOwner,
  type Credentials,
} from './support/api';

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000/api/v1';

async function signInUi(page: Page, creds: Credentials) {
  await page.goto('/auth/sign-in');
  await page.fill('input[formControlName="email"]', creds.ownerEmail);
  await page.fill('input[formControlName="password"]', creds.ownerPassword);
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

async function apiStatus(
  token: string,
  method: 'POST',
  path: string,
  body?: unknown,
): Promise<number> {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return response.status;
}

test.describe('Approval Queue (chunk 008 US2)', () => {
  let creds: Credentials;
  let ownerToken: string;

  test.beforeAll(async () => {
    creds = credentials();
    ownerToken = await signInOwner();
  });

  async function seedSubmittedRequest(label: string): Promise<{
    requestId: string;
    branchId: string;
    requesterId: string;
    requiredByDate: string;
  }> {
    const branch = await apiAsUser<{ id: string }>(
      ownerToken,
      'POST',
      '/organisation/branches',
      {
        name: `Approval E2E ${label} ${Date.now()}`,
        address: '42 Approval Road',
        region: 'GB',
      },
    );
    const product = await createTestProduct(ownerToken, {
      tenant_name: `Approval E2E Item ${label} ${Date.now()}`,
    });
    const requiredByDate = new Date(Date.now() + 30 * 86_400_000)
      .toISOString()
      .split('T')[0]!;
    const draft = await apiAsUser<{
      id: string;
      requested_by_membership_id: string;
    }>(ownerToken, 'POST', '/requests', {
      branch_id: branch.id,
      required_by_date: requiredByDate,
      lines: [{ workspace_product_id: product.id, quantity: '3' }],
    });
    const submitted = await apiAsUser<{
      id: string;
      requested_by_membership_id: string;
    }>(ownerToken, 'POST', `/requests/${draft.id}/submit`);

    return {
      requestId: submitted.id,
      branchId: branch.id,
      requesterId: submitted.requested_by_membership_id,
      requiredByDate,
    };
  }

  test('approver sees full queued context and approves the request', async ({ page }) => {
    const request = await seedSubmittedRequest('approve');

    await signInUi(page, creds);
    await ensureEnglish(page);
    await page.goto('/approvals');
    await expect(page.locator('.approval-queue-title')).toContainText('Approval Queue');

    const row = page.locator('tr.request-row', { hasText: request.branchId });
    await expect(row).toBeVisible();
    await expect(row).toContainText(request.requesterId);
    await expect(row).toContainText(request.requiredByDate);
    await expect(row).toContainText('1 line');

    await row.locator('.expand-lines-btn').click();
    await expect(page.locator('.line-item-row').first()).toBeVisible();

    await row.locator('.approve-btn').click();
    const dialog = page.locator('mat-dialog-container', { hasText: 'Approve Purchase Request' });
    await expect(dialog).toBeVisible();
    await dialog.locator('textarea').fill('Approved from the E2E queue');
    await dialog.locator('.confirm-btn').click();

    await expect(page.locator('mat-snack-bar-container')).toContainText('Request approved.');
    await expect(row).toHaveCount(0);
  });

  test('an unrelated member cannot decide another approver queue item', async () => {
    const request = await seedSubmittedRequest('refused');
    const unrelated = await createMember('buyer', ownerToken);
    const unrelatedToken = await signIn(unrelated.email, unrelated.password);

    const status = await apiStatus(
      unrelatedToken,
      'POST',
      `/requests/${request.requestId}/approve`,
      { comment: 'Trying to approve an unrelated request' },
    );

    expect(status).not.toBe(200);
    const stillSubmitted = await apiAsUser<{ status: string }>(
      ownerToken,
      'GET',
      `/requests/${request.requestId}`,
    );
    expect(stillSubmitted.status).toBe('submitted');
  });

  test('Arabic RTL layout renders the approval queue', async ({ page }) => {
    await seedSubmittedRequest('arabic');
    await signInUi(page, creds);
    await page.click('.account-btn');
    await page.locator('button[mat-menu-item]', { hasText: 'العربية' }).click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');

    await page.goto('/approvals');
    await expect(page.locator('.approval-queue-title')).toContainText('قائمة الاعتماد');
    await expect(page.locator('.approve-btn').first()).toContainText('اعتماد');
  });
});
