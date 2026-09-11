import { test, expect, type Page } from '@playwright/test';

import {
  apiAsUser,
  createIsolatedWorkspace,
  createMember,
  createTestProduct,
  signIn,
  type Credentials,
} from './support/api';
import { seedLandedCost } from './support/db';

/**
 * End-to-End tests for approval threshold routing (chunk R2.1 — value-tier approver routing).
 *
 * Covered:
 * - A low-value request routes to the junior approver configured for its tier.
 * - A high-value request routes to the senior approver configured for the upper tier.
 * - An active delegation redirects the resolved approver to the delegate.
 * - A request with no matching threshold rule falls back to the workspace owner.
 *
 * One isolated workspace per file: threshold rules and delegations are tenant-scoped config,
 * so the spec must not mutate the shared global owner workspace.
 */
test.describe('Approval threshold routing', () => {
  let workspace: Credentials;
  let ownerToken: string;
  let ownerMembershipId: string;
  let branchId: string;

  async function membershipIdForEmail(
    token: string,
    email: string,
  ): Promise<string> {
    const members = await apiAsUser<{ items: { id: string; email: string }[] }>(
      token,
      'GET',
      '/members?limit=100',
    );
    const found = members.items.find((m) => m.email === email);
    if (!found) {
      throw new Error(`membership not found for ${email}`);
    }
    return found.id;
  }

  test.beforeAll(async () => {
    workspace = await createIsolatedWorkspace();
    ownerToken = await signIn(workspace.ownerEmail, workspace.ownerPassword);

    ownerMembershipId = await membershipIdForEmail(ownerToken, workspace.ownerEmail);

    const branch = await apiAsUser<{ id: string }>(
      ownerToken,
      'POST',
      '/organisation/branches',
      {
        name: `Routing Branch ${Date.now()}`,
        address: '42 Threshold Road',
        region: 'GB',
      },
    );
    branchId = branch.id;
  });

  test.beforeEach(async () => {
    const rules = await apiAsUser<{ items: { id: string }[] }>(
      ownerToken,
      'GET',
      '/approvals/threshold-rules?limit=100',
    );
    for (const rule of rules.items) {
      await apiAsUser(ownerToken, 'DELETE', `/approvals/threshold-rules/${rule.id}`);
    }

    const delegations = await apiAsUser<{ items: { id: string }[] }>(
      ownerToken,
      'GET',
      '/approvals/delegations?limit=100',
    );
    for (const delegation of delegations.items) {
      await apiAsUser(ownerToken, 'DELETE', `/approvals/delegations/${delegation.id}`);
    }
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
      tenant_name: `Routing Product ${Date.now()}`,
    });
    seedLandedCost(workspace.ownerEmail, product.id, unitPrice, 'GBP');
    return product;
  }

  async function submitRequestAsBuyer(
    productId: string,
    quantity: string,
  ): Promise<{
    requestId: string;
    approvalStep: { assigned_membership_id: string; source: string } | null;
    estimatedTotal: { amount: string; currency: string } | null;
  }> {
    const buyer = await createMember('buyer', ownerToken);
    const buyerToken = await signIn(buyer.email, buyer.password);
    const requiredByDate = new Date(Date.now() + 30 * 86_400_000)
      .toISOString()
      .split('T')[0]!;

    const draft = await apiAsUser<{ id: string }>(buyerToken, 'POST', '/requests', {
      branch_id: branchId,
      required_by_date: requiredByDate,
      lines: [{ workspace_product_id: productId, quantity }],
    });

    const submitted = await apiAsUser<{
      id: string;
      approval_step: { assigned_membership_id: string; source: string } | null;
      estimated_total: { amount: string; currency: string } | null;
    }>(buyerToken, 'POST', `/requests/${draft.id}/submit`);

    return {
      requestId: submitted.id,
      approvalStep: submitted.approval_step,
      estimatedTotal: submitted.estimated_total,
    };
  }

  test('low-value request routes to the junior approver', async ({ page }) => {
    const junior = await createMember('approver', ownerToken);
    const juniorToken = await signIn(junior.email, junior.password);
    const juniorMembershipId = await membershipIdForEmail(ownerToken, junior.email);

    await apiAsUser(ownerToken, 'POST', '/approvals/threshold-rules', {
      branch_id: null,
      min_amount: '0',
      max_amount: '1000',
      currency: 'GBP',
      approver_membership_id: juniorMembershipId,
    });

    const product = await seedProduct('100.00');
    const { requestId, approvalStep } = await submitRequestAsBuyer(product.id, '5');

    expect(approvalStep?.source).toBe('threshold_match');
    expect(approvalStep?.assigned_membership_id).toBe(juniorMembershipId);

    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await page.goto(`/requests/${requestId}`);

    const section = page.locator('.approval-step');
    await expect(section).toBeVisible();
    await expect(section.locator('.approval-meta', { hasText: junior.email })).toBeVisible();
  });

  test('high-value request routes to the senior approver', async ({ page }) => {
    const junior = await createMember('approver', ownerToken);
    const juniorToken = await signIn(junior.email, junior.password);
    const juniorMembershipId = await membershipIdForEmail(ownerToken, junior.email);

    const senior = await createMember('approver', ownerToken);
    const seniorToken = await signIn(senior.email, senior.password);
    const seniorMembershipId = await membershipIdForEmail(ownerToken, senior.email);

    await apiAsUser(ownerToken, 'POST', '/approvals/threshold-rules', {
      branch_id: null,
      min_amount: '0',
      max_amount: '1000',
      currency: 'GBP',
      approver_membership_id: juniorMembershipId,
    });
    await apiAsUser(ownerToken, 'POST', '/approvals/threshold-rules', {
      branch_id: null,
      min_amount: '1000',
      max_amount: '10000',
      currency: 'GBP',
      approver_membership_id: seniorMembershipId,
    });

    const product = await seedProduct('500.00');
    const { requestId, approvalStep } = await submitRequestAsBuyer(product.id, '3');

    expect(approvalStep?.source).toBe('threshold_match');
    expect(approvalStep?.assigned_membership_id).toBe(seniorMembershipId);

    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await page.goto(`/requests/${requestId}`);

    const section = page.locator('.approval-step');
    await expect(section).toBeVisible();
    await expect(section.locator('.approval-meta', { hasText: senior.email })).toBeVisible();
    await expect(section.locator('.approval-meta', { hasText: junior.email })).toHaveCount(0);
  });

  test('active delegation redirects the resolved approver to the delegate', async ({ page }) => {
    const approver = await createMember('approver', ownerToken);
    const approverToken = await signIn(approver.email, approver.password);
    const approverMembershipId = await membershipIdForEmail(ownerToken, approver.email);

    const delegate = await createMember('buyer', ownerToken);
    const delegateToken = await signIn(delegate.email, delegate.password);
    const delegateMembershipId = await membershipIdForEmail(ownerToken, delegate.email);

    await apiAsUser(ownerToken, 'POST', '/approvals/threshold-rules', {
      branch_id: null,
      min_amount: '0',
      max_amount: '1000',
      currency: 'GBP',
      approver_membership_id: approverMembershipId,
    });

    const today = new Date().toISOString().split('T')[0];
    const future = new Date(Date.now() + 30 * 86_400_000).toISOString().split('T')[0];
    await apiAsUser(ownerToken, 'POST', '/approvals/delegations', {
      delegator_membership_id: approverMembershipId,
      delegate_membership_id: delegateMembershipId,
      starts_on: today,
      ends_on: future,
    });

    const product = await seedProduct('100.00');
    const { requestId, approvalStep } = await submitRequestAsBuyer(product.id, '5');

    expect(approvalStep?.source).toBe('delegate');
    expect(approvalStep?.assigned_membership_id).toBe(delegateMembershipId);

    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await page.goto(`/requests/${requestId}`);

    const section = page.locator('.approval-step');
    await expect(section).toBeVisible();
    await expect(section.locator('.approval-meta', { hasText: delegate.email })).toBeVisible();
    await expect(section.locator('.approval-meta', { hasText: approver.email })).toHaveCount(0);
  });

  test('request with no matching rule falls back to the owner', async ({ page }) => {
    const product = await seedProduct('100.00');
    const { requestId, approvalStep } = await submitRequestAsBuyer(product.id, '5');

    expect(approvalStep?.source).toBe('owner_fallback');
    expect(approvalStep?.assigned_membership_id).toBe(ownerMembershipId);

    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await page.goto(`/requests/${requestId}`);

    const section = page.locator('.approval-step');
    await expect(section).toBeVisible();
    await expect(section.locator('.approval-meta', { hasText: workspace.ownerEmail })).toBeVisible();
  });
});
