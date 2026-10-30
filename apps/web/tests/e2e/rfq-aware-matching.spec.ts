import { expect, test, type Page } from '@playwright/test';

import {
  apiAsUser,
  createIsolatedWorkspace,
  createTestProduct,
  createTestSupplier,
  signIn,
} from './support/api';
import { confirmQuotation } from './support/canonical-flow';
import { seedRfqReplyQuotationForReview } from './support/db';
import { openAsyncSelect } from './support/select';

async function signInUi(page: Page, email: string, password: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto('/auth/sign-in');
  await page.evaluate(() => localStorage.clear());
  await page.fill('input[formControlName="email"]', email);
  await page.fill('input[formControlName="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
}

/**
 * End-to-End test for RFQ-aware matching and match correction (spec 023, US1, T032).
 *
 * Requirements:
 * - FR-001/FR-002: RFQ reply quotation lines match against the RFQ's lines first.
 * - FR-003: Lines answering an RFQ line auto-match deterministically with no open tasks in the queue,
 *   explained as "From your RFQ line N".
 * - FR-005: A buyer can correct an automatic match decision on a quotation line; the correction
 *   supersedes the earlier decision and the queue/line reflects the corrected status.
 */
test.describe('RFQ-aware matching & match correction (023, US1, T032)', () => {
  test('auto-matches RFQ reply lines to RFQ items and supports match correction', async ({
    page,
  }) => {
    const stamp = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    const creds = await createIsolatedWorkspace();
    const token = await signIn(creds.ownerEmail, creds.ownerPassword);

    // 1. Create two distinct products in the catalogue with explicit pack definitions
    const product1Name = `Organic White Quinoa ${stamp}`;
    const product2Name = `Organic Red Lentils ${stamp}`;

    const product1 = await createTestProduct(token, {
      tenant_name: product1Name,
      base_unit: 'kilogram',
      pack_count: 1,
      unit_size: '10',
    });
    const product2 = await createTestProduct(token, {
      tenant_name: product2Name,
      base_unit: 'kilogram',
      pack_count: 1,
      unit_size: '25',
    });

    // Create 2 suppliers
    const supplier1 = await createTestSupplier(token, `Delta Wholesalers ${stamp}`);
    await apiAsUser(token, 'PATCH', `/suppliers/${supplier1.id}`, {
      contact_email: `delta_${stamp}@example.test`,
    });
    const supplier2 = await createTestSupplier(token, `Apex Commodities ${stamp}`);
    await apiAsUser(token, 'PATCH', `/suppliers/${supplier2.id}`, {
      contact_email: `apex_${stamp}@example.test`,
    });

    // Create and send an RFQ for the 2 products to both suppliers
    const neededByDate = new Date(Date.now() + 14 * 86_400_000).toISOString().split('T')[0]!;
    const rfqRes = await apiAsUser<{ rfq: { id: string } }>(
      token,
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
    const rfqId = rfqRes.rfq.id;

    await apiAsUser(
      token,
      'POST',
      `/rfq/${rfqId}/send`,
      {},
      {
        'Idempotency-Key': crypto.randomUUID(),
      },
    );

    // Seed reply quotations for both suppliers matching the RFQ lines and packs
    const quote1 = seedRfqReplyQuotationForReview(creds.ownerEmail, rfqId, supplier1.id, [
      {
        description: product1Name,
        quantity: '5',
        packCount: 1,
        unitSize: '10',
        packUnit: 'kilogram',
        unitPrice: '15.50',
      },
      {
        description: product2Name,
        quantity: '8',
        packCount: 1,
        unitSize: '25',
        packUnit: 'kilogram',
        unitPrice: '28.00',
      },
    ]);

    const quote2 = seedRfqReplyQuotationForReview(creds.ownerEmail, rfqId, supplier2.id, [
      {
        description: product1Name,
        quantity: '5',
        packCount: 1,
        unitSize: '10',
        packUnit: 'kilogram',
        unitPrice: '16.00',
      },
      {
        description: product2Name,
        quantity: '8',
        packCount: 1,
        unitSize: '25',
        packUnit: 'kilogram',
        unitPrice: '27.50',
      },
    ]);

    // 2. Authorize both quotations through the UI, as the canonical flow does
    await signInUi(page, creds.ownerEmail, creds.ownerPassword);

    // Authorize quote 1
    const quote1ReviewRes = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes(`/quotations/${quote1.quotationId}`) &&
        resp.ok(),
    );
    await page.goto(`/quotations/${quote1.quotationId}/review`);
    await quote1ReviewRes;
    await expect(page.locator('button.confirm-btn')).toBeEnabled({ timeout: 15000 });
    await confirmQuotation(page);

    // Authorize quote 2
    const quote2ReviewRes = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes(`/quotations/${quote2.quotationId}`) &&
        resp.ok(),
    );
    await page.goto(`/quotations/${quote2.quotationId}/review`);
    await quote2ReviewRes;
    await expect(page.locator('button.confirm-btn')).toBeEnabled({ timeout: 15000 });
    await confirmQuotation(page);

    // 3. Open the Match Resolution queue for those quotations:
    // It holds no open task, because every line auto-matched to its RFQ line.
    const queueTasksRes = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes('/matching/tasks') &&
        resp.ok(),
    );
    await page.goto(`/matching?quotation_id=${quote1.quotationId}`);
    await queueTasksRes;

    // Assert the empty state
    const emptyState = page.locator('[data-testid="quotation-all-matched"]');
    await expect(emptyState).toBeVisible({ timeout: 15000 });
    await expect(emptyState.locator('.empty-title')).toHaveText(
      /All lines of this quote are matched/i,
    );

    // Filter by the auto-matched status
    const statusSelect = page.locator('.filter-card mat-select').first();
    await openAsyncSelect(page, statusSelect);
    const autoTasksRes = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes('/matching/tasks') &&
        resp.url().includes('status=auto_accepted') &&
        resp.ok(),
    );
    await page.locator('mat-option', { hasText: /Auto-matched/ }).click();
    await autoTasksRes;

    // Assert that the auto-matched rows show "From your RFQ line N" (the queue chip)
    const quoteGroup = page.locator('.quotation-group', {
      hasText: quote1.quotationId.slice(0, 8),
    });
    await expect(quoteGroup).toHaveCount(1, { timeout: 15000 });
    const matchLines = quoteGroup.locator('.match-line');
    await expect(matchLines).toHaveCount(2);

    const rfqChips = quoteGroup.locator('.reason-chip.rfq-chip');
    await expect(rfqChips).toHaveCount(2);
    await expect(rfqChips.filter({ hasText: /From your RFQ line 1/i })).toHaveCount(1);
    await expect(rfqChips.filter({ hasText: /From your RFQ line 2/i })).toHaveCount(1);

    // 4. Correct one match: open that line, use Correct, and pick another existing product
    // (rank 2 in the candidate list) or a new product.
    const lineToCorrect = matchLines.filter({ hasText: /From your RFQ line 1/i }).first();
    const taskDetailRes = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes('/quotation-lines/') &&
        resp.ok(),
    );
    await lineToCorrect.locator('a.action-btn').click();
    await taskDetailRes;
    await page.waitForURL('**/matching/**');

    // Verify initial decision state on the line page
    const decisionBanner = page.locator('.decision-banner');
    await expect(decisionBanner).toBeVisible({ timeout: 15000 });
    await expect(decisionBanner.locator('.auto-tag')).toHaveText(/Automatic Match/i);
    await expect(decisionBanner.locator('.rfq-matched-tag')).toHaveText(/From your RFQ line 1/i);
    await expect(decisionBanner).toContainText(product1Name);

    // Click "Correct match" to open the dialog
    await decisionBanner.locator('.correct-match-btn').click();
    const dialog = page.locator('mat-dialog-container');
    await expect(dialog).toBeVisible();

    // Pick rank 2 in the candidate list (or create new product)
    const candidateChoices = dialog.locator('.dialog-candidate-item:not(.new-product-choice)');
    const candCount = await candidateChoices.count();
    let expectedProductName = '';

    if (candCount >= 2) {
      const rank2 = candidateChoices.nth(1);
      expectedProductName = (await rank2.locator('.cand-name').textContent())?.trim() ?? '';
      await rank2.click();
      await expect(rank2).toHaveClass(/selected/);
    } else {
      expectedProductName = `Replacement Product ${stamp}`;
      const newProductChoice = dialog.locator('.new-product-choice');
      await newProductChoice.click();
      await expect(newProductChoice).toHaveClass(/selected/);
      await dialog.locator('input[formControlName="tenant_name"]').fill(expectedProductName);
      await openAsyncSelect(page, dialog.locator('mat-select[formControlName="base_unit"]'));
      await page.locator('mat-option', { hasText: /kilogram/i }).click();
      await dialog.locator('input[formControlName="pack_count"]').fill('1');
      await dialog.locator('input[formControlName="unit_size"]').fill('10');
    }

    // Submit correction and wait on API response
    const correctionApiRes = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        /\/quotation-lines\/[^/]+\/match\/corrections$/.test(new URL(resp.url()).pathname) &&
        resp.ok(),
    );
    await dialog.locator('button.confirm-correction-btn').click();
    await correctionApiRes;
    await expect(dialog).toBeHidden();

    // Assert decision changed on the detail page
    await expect(decisionBanner).toContainText(expectedProductName);
    await expect(decisionBanner.locator('.human-tag')).toHaveText(/Human Resolution/i);

    // Return to queue and assert the line now shows "Corrected"
    const backQueueRes = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'GET' &&
        resp.url().includes('/matching/tasks') &&
        resp.ok(),
    );
    await page.locator('a.back-btn').click();
    await backQueueRes;

    const correctedLine = page.locator('.match-line', { hasText: expectedProductName });
    await expect(correctedLine).toHaveCount(1, { timeout: 15000 });
    await expect(correctedLine.locator('.reason-chip.reason-corrected')).toHaveText(/Corrected/i);
  });
});
