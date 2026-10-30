import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

import {
  apiAsUser,
  createIsolatedWorkspace,
  createTestProduct,
  createTestSupplier,
  pollBasketSplitJob,
  signIn,
  type Credentials,
} from './support/api';
import { confirmQuotation } from './support/canonical-flow';
import { seedRfqReplyQuotationForReview } from './support/db';
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

async function switchToArabic(page: Page): Promise<void> {
  if ((await page.locator('html').getAttribute('dir')) !== 'rtl') {
    await page.click('.account-btn');
    await page.locator('button[mat-menu-item]', { hasText: 'العربية' }).click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ar');
  }
}

/**
 * End-to-End test for splitting an RFQ between suppliers, preparing draft requests,
 * and approving them as one group (spec 024, T033, US1-US3).
 *
 * Requirements:
 * 1. Seed RFQ for 2 products and 2 suppliers, with 2 reviewed, fully matched replies
 *    priced so the split is cheaper than either single supplier.
 * 2. RFQ compare page → "Split between suppliers" → Basket Split in RFQ mode.
 *    Wait for job via API polling helper. Assert split total, baselines, and saving.
 * 3. "Prepare 2 requests" → fill branch and required-by → submit → summary shows 2 requests.
 * 4. Open one request → "Part of a split · 1 of 2" → Submit (group submit).
 * 5. Sign in as approver/owner → queue shows ONE row for split → Approve → both requests are ordered.
 * 6. Arabic RTL pass on approval queue & basket split RFQ mode with zero axe violations @a11y.
 */
test.describe.serial('RFQ basket split & group approval flow (024, T033)', () => {
  let workspace: Credentials;
  let ownerToken: string;
  let branchName: string;
  let supplier1Name: string;
  let supplier2Name: string;
  let rfqId: string;
  let neededByDate: string;
  let quote1Id: string;
  let quote2Id: string;
  let basketJobId: string;
  let createdRequestIds: string[] = [];

  test.beforeAll(async () => {
    const stamp = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    workspace = await createIsolatedWorkspace('GBP');
    ownerToken = await signIn(workspace.ownerEmail, workspace.ownerPassword);

    branchName = `Branch ${stamp}`;
    await apiAsUser<{ id: string; name: string }>(
      ownerToken,
      'POST',
      '/organisation/branches',
      {
        name: branchName,
        address: '10 Queensway',
        region: 'GB',
      },
      { 'Idempotency-Key': crypto.randomUUID() },
    );

    const product1Name = `Product Alpha ${stamp}`;
    const product2Name = `Product Beta ${stamp}`;

    const product1 = await createTestProduct(ownerToken, {
      tenant_name: product1Name,
      base_unit: 'kilogram',
      pack_count: 1,
      unit_size: '10',
    });
    const product2 = await createTestProduct(ownerToken, {
      tenant_name: product2Name,
      base_unit: 'kilogram',
      pack_count: 1,
      unit_size: '25',
    });

    supplier1Name = `Supplier One ${stamp}`;
    supplier2Name = `Supplier Two ${stamp}`;

    const supplier1 = await createTestSupplier(ownerToken, supplier1Name);
    await apiAsUser(ownerToken, 'PATCH', `/suppliers/${supplier1.id}`, {
      contact_email: `supp1_${stamp}@example.test`,
    });
    const supplier2 = await createTestSupplier(ownerToken, supplier2Name);
    await apiAsUser(ownerToken, 'PATCH', `/suppliers/${supplier2.id}`, {
      contact_email: `supp2_${stamp}@example.test`,
    });

    neededByDate = new Date(Date.now() + 14 * 86_400_000).toISOString().split('T')[0]!;
    const rfqRes = await apiAsUser<{ rfq: { id: string } }>(
      ownerToken,
      'POST',
      '/rfq',
      {
        lines: [
          { workspace_product_id: product1.id, quantity: '5' },
          { workspace_product_id: product2.id, quantity: '8' },
        ],
        recipient_supplier_ids: [supplier1.id, supplier2.id],
        needed_by_date: neededByDate,
        tenant_terms: 'Payment terms: net 30 days.',
      },
      { 'Idempotency-Key': crypto.randomUUID() },
    );
    rfqId = rfqRes.rfq.id;

    await apiAsUser(
      ownerToken,
      'POST',
      `/rfq/${rfqId}/send`,
      {},
      { 'Idempotency-Key': crypto.randomUUID() },
    );

    // Seed replies where supplier 1 is cheaper on product 1 (10.00 vs 20.00)
    // and supplier 2 is cheaper on product 2 (15.00 vs 30.00).
    // Supplier 1 total: 5 * 10 + 8 * 30 = 290.00.
    // Supplier 2 total: 5 * 20 + 8 * 15 = 220.00.
    // Split total: 5 * 10 + 8 * 15 = 170.00.
    // Saving against best single (220.00): 50.00.
    const quote1 = seedRfqReplyQuotationForReview(
      workspace.ownerEmail,
      rfqId,
      supplier1.id,
      [
        {
          description: product1Name,
          quantity: '5',
          packCount: 1,
          unitSize: '10',
          packUnit: 'kilogram',
          unitPrice: '10.00',
        },
        {
          description: product2Name,
          quantity: '8',
          packCount: 1,
          unitSize: '25',
          packUnit: 'kilogram',
          unitPrice: '30.00',
        },
      ],
      'GBP',
    );
    quote1Id = quote1.quotationId;

    const quote2 = seedRfqReplyQuotationForReview(
      workspace.ownerEmail,
      rfqId,
      supplier2.id,
      [
        {
          description: product1Name,
          quantity: '5',
          packCount: 1,
          unitSize: '10',
          packUnit: 'kilogram',
          unitPrice: '20.00',
        },
        {
          description: product2Name,
          quantity: '8',
          packCount: 1,
          unitSize: '25',
          packUnit: 'kilogram',
          unitPrice: '15.00',
        },
      ],
      'GBP',
    );
    quote2Id = quote2.quotationId;
  });

  test('splits an RFQ between suppliers, prepares requests and approves them as one', async ({
    page,
  }) => {
    // 1. Authorize both quotations through the UI to complete review and auto-matching
    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);

    const quote1ReviewRes = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes(`/quotations/${quote1Id}`) &&
        resp.ok(),
    );
    await page.goto(`/quotations/${quote1Id}/review`);
    await quote1ReviewRes;
    await expect(page.locator('button.confirm-btn')).toBeEnabled({ timeout: 15000 });
    await confirmQuotation(page);

    const quote2ReviewRes = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes(`/quotations/${quote2Id}`) &&
        resp.ok(),
    );
    await page.goto(`/quotations/${quote2Id}/review`);
    await quote2ReviewRes;
    await expect(page.locator('button.confirm-btn')).toBeEnabled({ timeout: 15000 });
    await confirmQuotation(page);

    // 2. RFQ compare page → "Split between suppliers" → Basket Split page in RFQ mode
    const compareResponsesRes = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes(`/rfq/${rfqId}/responses`) &&
        resp.ok(),
    );
    await page.goto(`/rfq/compare/${rfqId}`);
    await compareResponsesRes;

    const splitBtn = page.locator('[data-testid="rfq-compare-split-button"]');
    await expect(splitBtn).toBeEnabled({ timeout: 15000 });

    const splitPostPromise = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().includes(`/rfq/${rfqId}/split`) &&
        resp.ok(),
    );
    await splitBtn.click();
    const splitPostRes = await splitPostPromise;
    const splitJobData = (await splitPostRes.json()) as { id: string };
    basketJobId = splitJobData.id;

    await page.waitForURL(`**/offers/basket-split/${basketJobId}`);

    // Wait for the job to complete, polling the API through a support helper rather than sleeping
    const completedJob = await pollBasketSplitJob(ownerToken, basketJobId);
    expect(completedJob.status).toBe('completed');

    // Assert the split total, both single-supplier totals and the saving
    const savingsSummary = page.locator('[data-testid="rfq-savings-summary"]');
    await expect(savingsSummary).toBeVisible({ timeout: 15000 });

    await expect(savingsSummary.locator('.split-card .total-figure')).toContainText('GBP 170');
    await expect(savingsSummary.locator('.saving-card .total-figure')).toContainText('GBP 50');

    const baselineCards = savingsSummary.locator('.baseline-card');
    await expect(baselineCards.filter({ hasText: supplier1Name })).toContainText('GBP 290');
    await expect(baselineCards.filter({ hasText: supplier2Name })).toContainText('GBP 220');

    // 3. "Prepare 2 requests" → fill the dialog (branch, required-by) → submit
    const prepareBtn = page.locator('[data-testid="prepare-requests-button"]');
    await expect(prepareBtn).toBeVisible({ timeout: 15000 });
    await prepareBtn.click();

    const prepareDialog = page.locator('mat-dialog-container');
    await expect(prepareDialog).toBeVisible({ timeout: 10000 });

    const branchSelect = prepareDialog.locator('mat-select[formControlName="branch_id"]');
    const branchText = await branchSelect.textContent();
    if (!branchText || !branchText.includes(branchName)) {
      await openAsyncSelect(page, branchSelect);
      await page.locator('mat-option', { hasText: branchName }).click();
    }

    const reqByInput = prepareDialog.locator('input[formControlName="required_by_date"]');
    if (!(await reqByInput.inputValue())) {
      await reqByInput.fill(neededByDate);
    }

    const prepareRequestsPromise = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().includes(`/baskets/${basketJobId}/prepare-requests`) &&
        resp.ok(),
    );
    await prepareDialog.locator('button.mat-mdc-unelevated-button[color="primary"]').click();
    const prepareResponse = await prepareRequestsPromise;
    const prepareResult = (await prepareResponse.json()) as { purchase_request_ids: string[] };
    createdRequestIds = prepareResult.purchase_request_ids;
    expect(createdRequestIds).toHaveLength(2);

    // Summary lists 2 requests, each with its supplier
    const preparedSummary = page.locator('[data-testid="prepared-requests-summary"]');
    await expect(preparedSummary).toBeVisible({ timeout: 15000 });
    const requestItems = preparedSummary.locator('[data-testid="prepared-request-item"]');
    await expect(requestItems).toHaveCount(2);
    await expect(requestItems.filter({ hasText: supplier1Name })).toHaveCount(1);
    await expect(requestItems.filter({ hasText: supplier2Name })).toHaveCount(1);

    // 4. Open one of the requests → "Part of a split · 1 of 2" → Submit (group submit)
    const viewFirstLink = requestItems.first().locator('[data-testid="view-request-link"]');
    const requestDetailPromise = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes('/requests/') &&
        resp.ok(),
    );
    await viewFirstLink.click();
    await requestDetailPromise;
    await page.waitForURL('**/requests/**');

    const splitInfoLine = page.locator('[data-testid="split-info-line"]');
    await expect(splitInfoLine).toBeVisible({ timeout: 15000 });
    await expect(splitInfoLine.locator('.split-context-text')).toContainText('Part of a split · 1 of 2');

    const groupSubmitPromise = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().includes('/request-groups/') &&
        resp.url().endsWith('/submit') &&
        resp.ok(),
    );
    const submitBtn = page.locator('button.submit-request-btn');
    await expect(submitBtn).toBeEnabled({ timeout: 10000 });
    await submitBtn.click();
    await groupSubmitPromise;
    // Submitting returns to the request list, where both requests of the split are submitted
    await page.waitForURL('**/requests');
    const splitRows = page.locator('tr').filter({ has: page.locator('[data-testid="split-badge"]') });
    await expect(splitRows).toHaveCount(2, { timeout: 15000 });
    await expect(splitRows.filter({ hasText: supplier1Name })).toContainText(/Submitted/i);
    await expect(splitRows.filter({ hasText: supplier2Name })).toContainText(/Submitted/i);

    // 5. Sign in as approver/owner → approval queue shows ONE row for split → Approve
    const pendingApprovalsPromise = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes('/approvals/pending') &&
        resp.ok(),
    );
    await page.goto('/approvals');
    await pendingApprovalsPromise;

    const splitGroupSummary = page.locator('[data-testid="split-group-summary"]');
    await expect(splitGroupSummary).toHaveCount(1, { timeout: 15000 });
    await expect(splitGroupSummary).toContainText('Split from RFQ');

    const groupRow = page.locator('tr.request-row').filter({ has: splitGroupSummary });
    await expect(groupRow).toBeVisible();

    await groupRow.locator('button.approve-btn').click();
    const decisionDialog = page.locator('mat-dialog-container');
    await expect(decisionDialog).toBeVisible({ timeout: 10000 });

    const groupApprovePromise = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().includes('/request-groups/') &&
        resp.url().endsWith('/approve') &&
        resp.ok(),
    );
    await decisionDialog.locator('.confirm-btn').click();
    await groupApprovePromise;

    // Both requests are ordered (check via the API helper)
    const req1 = await apiAsUser<{ status: string }>(
      ownerToken,
      'GET',
      `/requests/${createdRequestIds[0]}`,
    );
    const req2 = await apiAsUser<{ status: string }>(
      ownerToken,
      'GET',
      `/requests/${createdRequestIds[1]}`,
    );
    expect(req1.status).toBe('ordered');
    expect(req2.status).toBe('ordered');

    // 6. Arabic RTL pass directly in the current flow
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.approval-queue-title')).toContainText('قائمة الاعتماد');
    await page.waitForLoadState('networkidle');
    const approvalsAxe = await scan(page);
    expect(approvalsAxe.violations, describeViolations(approvalsAxe)).toEqual([]);
  });

  test('renders approval queue and basket split in Arabic (RTL) with zero WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await switchToArabic(page);

    // 1. Scan approval queue in Arabic
    const pendingApprovalsPromise = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes('/approvals/pending') &&
        resp.ok(),
    );
    await page.goto('/approvals');
    await pendingApprovalsPromise;
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.approval-queue-title')).toContainText('قائمة الاعتماد');
    await page.waitForLoadState('networkidle');
    const approvalsResults = await scan(page);
    expect(approvalsResults.violations, describeViolations(approvalsResults)).toEqual([]);

    // 2. Scan basket split RFQ mode page in Arabic if job ID is available
    if (basketJobId) {
      const basketJobPromise = page.waitForResponse(
        (resp) =>
          resp.request().method() === 'GET' &&
          resp.url().includes(`/baskets/${basketJobId}`) &&
          resp.ok(),
      );
      await page.goto(`/offers/basket-split/${basketJobId}`);
      await basketJobPromise;
      await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
      await page.waitForLoadState('networkidle');
      const basketResults = await scan(page);
      expect(basketResults.violations, describeViolations(basketResults)).toEqual([]);
    }
  });
});
