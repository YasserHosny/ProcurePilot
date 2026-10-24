import { test, expect, type Page } from '@playwright/test';

import {
  apiAsUser,
  createIsolatedWorkspace,
  createMember,
  createTestProduct,
  signIn,
  type Credentials,
  type CreatedMember,
} from './support/api';
import { seedLandedCost } from './support/db';

/**
 * End-to-End tests for request budget status (chunk R2.1 — budget-aware request visibility).
 *
 * Covered:
 * - A requester sees a budget-exceeded warning on their request's detail page.
 * - A requester sees remaining budget when the request is within budget.
 * - An approver sees the budget-exceeded warning against the request in the approval queue.
 *
 * One isolated workspace per file: budgets are tenant-scoped config and committed spend from
 * earlier tests must not leak across periods.
 */
test.describe('Request budget status', () => {
  let workspace: Credentials;
  let ownerToken: string;
  let branchId: string;

  test.beforeAll(async () => {
    workspace = await createIsolatedWorkspace();
    ownerToken = await signIn(workspace.ownerEmail, workspace.ownerPassword);

    const branch = await apiAsUser<{ id: string }>(
      ownerToken,
      'POST',
      '/organisation/branches',
      {
        name: `Budget Branch ${Date.now()}`,
        address: '9 Ledger Lane',
        region: 'GB',
      },
      { 'Idempotency-Key': crypto.randomUUID() },
    );
    branchId = branch.id;
  });

  async function signInUi(page: Page, email: string, password: string): Promise<void> {
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', email);
    await page.fill('input[formControlName="password"]', password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  }

  async function seedProduct(unitPrice: string): Promise<{ id: string; tenant_name: string }> {
    const product = await createTestProduct(ownerToken, {
      tenant_name: `Budget Product ${Date.now()}`,
    });
    seedLandedCost(workspace.ownerEmail, product.id, unitPrice, 'GBP');
    return product;
  }

  async function submitRequestAsBuyer(
    productId: string,
    quantity: string,
    requiredByDate: string,
  ): Promise<{
    requestId: string;
    buyer: CreatedMember;
    budgetStatus: {
      status: 'within' | 'near' | 'over' | 'no_budget';
      exceeds: boolean;
      remaining_amount: { amount: string; currency: string } | null;
      reason_code: string | null;
    };
  }> {
    const buyer = await createMember('buyer', ownerToken);
    const buyerToken = await signIn(buyer.email, buyer.password);

    const draft = await apiAsUser<{ id: string }>(buyerToken, 'POST', '/requests', {
      branch_id: branchId,
      required_by_date: requiredByDate,
      lines: [{ workspace_product_id: productId, quantity }],
    }, { 'Idempotency-Key': crypto.randomUUID() });

    const submitted = await apiAsUser<{
      id: string;
      budget_status: {
        status: 'within' | 'near' | 'over' | 'no_budget';
        exceeds: boolean;
        remaining_amount: { amount: string; currency: string } | null;
        reason_code: string | null;
      };
    }>(buyerToken, 'POST', `/requests/${draft.id}/submit`, {}, { 'Idempotency-Key': crypto.randomUUID() });

    return {
      requestId: submitted.id,
      buyer,
      budgetStatus: submitted.budget_status,
    };
  }

  test('requester sees a budget-exceeded warning on the detail page', async ({ page }) => {
    const periodStart = '2030-01-01';
    const requiredBy = '2030-01-15';

    await apiAsUser(ownerToken, 'POST', '/organisation/budgets', {
      amount: '1000',
      currency: 'GBP',
      period: 'monthly',
      period_start: periodStart,
      scope: 'organisation',
    }, { 'Idempotency-Key': crypto.randomUUID() });

    const product = await seedProduct('500.00');
    const { requestId, buyer, budgetStatus } = await submitRequestAsBuyer(
      product.id,
      '3',
      requiredBy,
    );

    expect(budgetStatus?.exceeds).toBe(true);

    await signInUi(page, buyer.email, buyer.password);
    await page.goto(`/requests/${requestId}`);

    const warning = page.locator('.budget-warning-banner');
    await expect(warning).toBeVisible();
    await expect(warning.locator('.budget-warning-message')).toContainText(
      'would exceed the remaining budget',
    );
    await expect(warning.locator('.budget-remaining-amount')).toContainText('GBP 1,000');

    // The page must show the request detail, not an error, for the requester.
    await expect(page.locator('.total-value')).toContainText('GBP 1,500');
  });

  test('requester sees remaining budget when the request is within budget', async ({ page }) => {
    const periodStart = '2030-02-01';
    const requiredBy = '2030-02-15';

    await apiAsUser(ownerToken, 'POST', '/organisation/budgets', {
      amount: '2000',
      currency: 'GBP',
      period: 'monthly',
      period_start: periodStart,
      scope: 'organisation',
    }, { 'Idempotency-Key': crypto.randomUUID() });

    const product = await seedProduct('100.00');
    const { requestId, buyer, budgetStatus } = await submitRequestAsBuyer(
      product.id,
      '5',
      requiredBy,
    );

    expect(budgetStatus.status).toBe('within');
    expect(budgetStatus.exceeds).toBe(false);
    expect(Number(budgetStatus.remaining_amount?.amount)).toBe(2000);
    expect(budgetStatus.remaining_amount?.currency).toBe('GBP');

    await signInUi(page, buyer.email, buyer.password);
    await page.goto(`/requests/${requestId}`);

    // Within budget the UI shows the remaining amount without a warning.
    await expect(page.locator('.budget-warning-banner')).toHaveCount(0);
    await expect(page.locator('.budget-status-row')).toHaveCount(1);
    await expect(page.locator('.budget-status-row')).toContainText('GBP 2,000');
    await expect(page.locator('.total-value')).toContainText('GBP 500');
  });

  test('approver sees a budget-exceeded warning in the approval queue', async ({ page }) => {
    const periodStart = '2030-03-01';
    const requiredBy = '2030-03-15';

    await apiAsUser(ownerToken, 'POST', '/organisation/budgets', {
      amount: '1000',
      currency: 'GBP',
      period: 'monthly',
      period_start: periodStart,
      scope: 'organisation',
    }, { 'Idempotency-Key': crypto.randomUUID() });

    const product = await seedProduct('500.00');
    const { budgetStatus } = await submitRequestAsBuyer(product.id, '3', requiredBy);

    expect(budgetStatus?.exceeds).toBe(true);

    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await page.goto('/approvals');

    // 008's own T043 only requires the warning inline in the approval-queue row — there is no
    // "view request detail" navigation affordance in this table (approval-queue.component.html's
    // actions column is expand-lines/approve/reject only), so this test doesn't invent a
    // drill-through the real UI never built.
    const row = page
      // The queue renders the required-by date locale-formatted (PPS-48): 2030-03-15 → Mar 15, 2030.
      .locator('tr.request-row', { hasText: 'Mar 15, 2030' })
      .filter({ hasText: 'GBP 1,500' });
    await expect(row).toBeVisible();
    await expect(row.locator('.budget-warning-badge')).toBeVisible();
    await expect(row.locator('.budget-warning-badge')).toContainText('Exceeds budget');
  });
});
