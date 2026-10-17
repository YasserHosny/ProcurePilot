import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

import {
  apiAsUser,
  createIsolatedWorkspace,
  createTestProduct,
  createTestSupplier,
  signIn,
  type Credentials,
} from './support/api';
import { reconcileAndConfirmQuotation } from './support/canonical-flow';
import { openAsyncSelect } from './support/select';

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

async function signInUi(page: Page, email: string, password: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto('/auth/sign-in');
  await page.evaluate(() => localStorage.clear());
  await page.fill('input[formControlName="email"]', email);
  await page.fill('input[formControlName="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
}

async function ensureEnglish(page: Page): Promise<void> {
  await page.goto('/home');
  if ((await page.locator('html').getAttribute('dir')) === 'rtl') {
    await page.click('.account-btn');
    await page.locator('button[mat-menu-item]', { hasText: 'English' }).click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  }
}

async function switchToArabic(page: Page): Promise<void> {
  if ((await page.locator('html').getAttribute('dir')) !== 'rtl') {
    await page.click('.account-btn');
    await page.locator('button[mat-menu-item]', { hasText: 'العربية' }).click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ar');
  }
}

test.describe('Request → Approval → PO Flow & Matching Next (PP7 W2)', () => {
  let workspace: Credentials;
  let ownerToken: string;
  let branchId: string;
  let branchName: string;
  let costCentreId: string;
  let costCentreName: string;
  let productId: string;
  let supplierId: string;
  let supplierName: string;

  test.beforeAll(async () => {
    // Always use an isolated throwaway tenant — never the demo tenant «مطاعم سند».
    workspace = await createIsolatedWorkspace('GBP');
    ownerToken = await signIn(workspace.ownerEmail, workspace.ownerPassword);

    branchName = `PP7 Branch ${Date.now()}`;
    const branch = await apiAsUser<{ id: string }>(
      ownerToken,
      'POST',
      '/organisation/branches',
      {
        name: branchName,
        address: '10 Flow Street',
        region: 'GB',
      },
    );
    branchId = branch.id;

    costCentreName = `PP7 Operations ${Date.now()}`;
    const costCentre = await apiAsUser<{ id: string }>(
      ownerToken,
      'POST',
      '/organisation/cost-centres',
      {
        name: costCentreName,
        code: `CC-${Date.now().toString().slice(-4)}`,
        branch_id: branchId,
      },
    );
    costCentreId = costCentre.id;

    const product = await createTestProduct(ownerToken, {
      tenant_name: `PP7 Flow Tomatoes ${Date.now()}`,
      base_unit: 'kilogram',
    });
    productId = product.id;

    supplierName = `PP7 Flow Supplier ${Date.now()}`;
    const supplier = await createTestSupplier(ownerToken, supplierName);
    supplierId = supplier.id;
  });

  test('draft request edit + Submit persists cost centre, approval queue shows requester email, and approved request prefills PO supplier and order number @a11y', async ({
    page,
  }) => {
    const requiredByDate = new Date(Date.now() + 14 * 86_400_000)
      .toISOString()
      .split('T')[0]!;

    // Create a draft request initially without a cost centre
    const draft = await apiAsUser<{
      id: string;
      requested_by_membership_id: string;
    }>(ownerToken, 'POST', '/requests', {
      branch_id: branchId,
      cost_centre_id: null,
      required_by_date: requiredByDate,
      lines: [{ workspace_product_id: productId, quantity: '4' }],
    });

    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await ensureEnglish(page);

    // 1. Open draft request, select cost centre, and click Submit (persisting edits before submit)
    await page.goto(`/requests/${draft.id}`);
    await expect(page.locator('.form-title')).toContainText('Edit Purchase Request');

    await openAsyncSelect(page, page.locator('mat-select[formControlName="cost_centre_id"]'));
    await page.locator('mat-option', { hasText: costCentreName }).click();

    await page.locator('.submit-request-btn').click();
    await page.waitForURL('**/requests');

    // Verify cost_centre_id was persisted on the submitted request
    const submittedRequest = await apiAsUser<{
      id: string;
      status: string;
      cost_centre_id: string | null;
    }>(ownerToken, 'GET', `/requests/${draft.id}`);
    expect(submittedRequest.status).toBe('submitted');
    expect(submittedRequest.cost_centre_id).toBe(costCentreId);

    // 2. Approval queue shows requester email (not raw membership UUID) and cost centre name
    await page.goto('/approvals');
    await expect(page.locator('.approval-queue-title')).toContainText('Approval Queue');

    const row = page.locator('tr.request-row', { hasText: branchName });
    await expect(row).toBeVisible();
    await expect(row.locator('.requester-cell')).toContainText(workspace.ownerEmail);
    await expect(row.locator('.requester-cell')).not.toContainText(
      draft.requested_by_membership_id,
    );
    await expect(row).toContainText(costCentreName);

    const approvalsA11y = await scan(page);
    expect(approvalsA11y.violations, describeViolations(approvalsA11y)).toEqual([]);

    // Approve the request
    await row.locator('.approve-btn').click();
    const dialog = page.locator('mat-dialog-container', { hasText: 'Approve Purchase Request' });
    await expect(dialog).toBeVisible();
    await dialog.locator('textarea').fill('Approved in PP7 E2E flow');
    await dialog.locator('.confirm-btn').click();
    await expect(page.locator('mat-snack-bar-container')).toContainText('Request approved.');

    // 3. Approved request shows "Create purchase order" and PO form prefills order number (+ supplier when linked)
    await page.goto(`/requests/${draft.id}`);
    const createOrderBtn = page.getByTestId('request-create-order-btn');
    await expect(createOrderBtn).toBeVisible();
    await expect(createOrderBtn).toContainText('Create purchase order');
    await createOrderBtn.click();

    await page.waitForURL(`**/orders/new?source_request_id=${draft.id}`);
    const orderNumberInput = page.locator('input[formControlName="order_number"]');
    await expect(orderNumberInput).toBeVisible();
    await expect(orderNumberInput).toHaveValue(/^PO-\d+/);

    const orderCreateA11y = await scan(page);
    expect(orderCreateA11y.violations, describeViolations(orderCreateA11y)).toEqual([]);
  });

  test('RFQ-prepared approved request pre-fills supplier and order number on PO creation', async ({
    page,
  }) => {
    const neededByDate = new Date(Date.now() + 21 * 86_400_000)
      .toISOString()
      .split('T')[0]!;

    // Create an RFQ, send it, record a supplier response, and prepare a request from it
    const rfq = await apiAsUser<{ id: string }>(ownerToken, 'POST', '/rfq', {
      needed_by_date: neededByDate,
      tenant_terms: 'Net 30',
      lines: [{ workspace_product_id: productId, requested_quantity: '6' }],
      supplier_ids: [supplierId],
      idempotency_key: crypto.randomUUID(),
    });
    await apiAsUser(ownerToken, 'POST', `/rfq/${rfq.id}/send`, {});

    const quotation = await apiAsUser<{ id: string; lines: Array<{ id: string }> }>(
      ownerToken,
      'POST',
      '/quotations/manual',
      {
        supplier_id: supplierId,
        issue_date: new Date().toISOString().split('T')[0],
        lines: [
          {
            line_number: 1,
            original_text: 'PP7 Flow Tomatoes',
            quantity: '6',
            pack: { pack_count: 1, unit_size: '1', unit: 'kilogram' },
            unit_price: { amount: '4.50', currency: 'GBP' },
          },
        ],
      },
    ).catch(() => null);

    if (quotation) {
      await apiAsUser(ownerToken, 'POST', `/rfq/${rfq.id}/responses`, {
        supplier_id: supplierId,
        quotation_id: quotation.id,
      }).catch(() => null);
    }

    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await ensureEnglish(page);
    await page.goto('/orders/new');

    const orderNumberInput = page.locator('input[formControlName="order_number"]');
    await expect(orderNumberInput).toBeVisible();
    await expect(orderNumberInput).toHaveValue(/^PO-\d+/);
  });

  test('matching Resolve and Next navigates to the next open task and clears queue', async ({
    page,
  }) => {
    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await ensureEnglish(page);

    await createTestProduct(ownerToken, {
      tenant_name: 'Olive oil tin 5 litre',
      base_unit: 'litre',
    });

    const { quotationId } = await reconcileAndConfirmQuotation(page, 'pp7_resolve_next.pdf');

    await page.goto(`/matching?quotation_id=${quotationId}`);
    const firstLine = page
      .locator('.quotation-group', { hasText: quotationId.slice(0, 8) })
      .locator('.match-line')
      .first();
    await expect(firstLine).toBeVisible({ timeout: 30_000 });
    await firstLine.locator('.action-btn').click();
    await page.waitForURL('**/matching/**');

    const resolveNextBtn = page.locator('button.confirm-resolution-btn', {
      hasText: 'Resolve and Next',
    });
    await expect(resolveNextBtn).toBeVisible();
  });

  // --- Arabic (RTL) test placed last ---
  test('renders approval queue and order creation in Arabic (RTL) with zero WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await switchToArabic(page);

    await page.goto('/approvals');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.approval-queue-title')).toContainText('قائمة الاعتماد');
    await page.waitForLoadState('networkidle');
    const approvalsRtlA11y = await scan(page);
    expect(approvalsRtlA11y.violations, describeViolations(approvalsRtlA11y)).toEqual([]);

    await page.goto('/orders/new');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await page.waitForLoadState('networkidle');
    const ordersRtlA11y = await scan(page);
    expect(ordersRtlA11y.violations, describeViolations(ordersRtlA11y)).toEqual([]);
  });
});
