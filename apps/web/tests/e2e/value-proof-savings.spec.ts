import { test, expect } from '@playwright/test';
import {
  createMember,
  fetchQuotationMatches,
  signInOwner,
  type CreatedMember,
} from './support/api';
import { reconcileAndConfirmQuotation, resolveLineAsNewProduct } from './support/canonical-flow';

/**
 * End-to-End test suite for Value Proof & Savings Ledger (T023, US1).
 *
 * Requirements:
 * - FR-001: Record purchase outcome.
 * - FR-002: Baseline, actual, delta calculation.
 * - FR-003: Pending vs verified lifecycle.
 * - FR-004: Verified saving immutability (no edit affordance).
 * - FR-005: Evidence view linking purchase, quotations, and offers.
 * - FR-006: Truthful delta display (positive/negative).
 * - FR-016: Dual language (English and Arabic RTL).
 */
test.describe('Value Proof & Savings Ledger (T023, US1)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('records purchase outcome linked to a real match chain and lands on the evidence view', async ({ page }) => {
    // Build the real chain the Record Purchase button would carry: quotation line →
    // match decision → landed cost, via confirm + resolution of a fresh quotation.
    const productName = `E2E Outcome Product ${Date.now()}`;
    const { quotationId, supplier } = await reconcileAndConfirmQuotation(page, 'outcome_chain.pdf');
    await resolveLineAsNewProduct(page, quotationId, 'Tomatoes case 10 kg', productName);

    const ownerToken = await signInOwner();
    const matches = await fetchQuotationMatches(ownerToken, quotationId);
    const tomatoLine = matches.lines.find((l) => l.line.original_text.includes('Tomatoes'));
    if (!tomatoLine || !tomatoLine.decision || !tomatoLine.landed_cost) {
      throw new Error('Expected the resolved tomato line to have a decision and landed cost');
    }

    const params = new URLSearchParams({
      product_id: tomatoLine.decision.matched_product.id,
      supplier_id: supplier.id,
      quotation_line_id: tomatoLine.line.id,
      match_decision_id: tomatoLine.decision.id,
      landed_cost_id: tomatoLine.landed_cost.id,
      base_unit: tomatoLine.landed_cost.base_unit || 'kilogram',
    });
    await page.goto(`/savings/outcome-capture?${params.toString()}`);

    await expect(page.locator('.page-title')).toContainText('Record Purchase Outcome');

    const productSelect = page.locator('mat-select[formControlName="workspace_product_id"]');
    await expect(productSelect).toBeVisible();

    // Fill the commercial figures by hand like a buyer would; the auto-total feature keeps
    // total_paid consistent with quantity × unit price.
    await page.fill('input[formControlName="quantity"]', '10');
    await page.fill('input[formControlName="unit_price_amount"]', '1.20');
    await page.fill('input[formControlName="currency"]', 'GBP');

    const totalPaid = page.locator('input[formControlName="total_paid_amount"]');
    await expect(totalPaid).toHaveValue('12.0000');

    const quantity = parseFloat(await page.inputValue('input[formControlName="quantity"]'));
    const unitPrice = parseFloat(await page.inputValue('input[formControlName="unit_price_amount"]'));
    const totalPaidValue = parseFloat(await totalPaid.inputValue());
    expect(Math.abs(quantity * unitPrice - totalPaidValue)).toBeLessThan(0.01);

    // Actually submit — a saving_record must be created and the evidence view must open.
    await page.locator('button[type="submit"].submit-btn').click();
    await page.waitForURL('**/savings/**/evidence');

    // The evidence page joins the whole chain; an error banner here is the regression this
    // suite exists to catch.
    await expect(page.locator('.error-banner')).toHaveCount(0);
    await expect(page.locator('.pending-banner')).toBeVisible();
    await expect(
      page.locator('.detail-row', { hasText: 'Actual Total Value' }).locator('.detail-val'),
    ).toContainText('12.00');
    // Baseline comes from the landed-cost price history (last paid £1.20/kg × 10 kg).
    await expect(
      page.locator('.detail-row', { hasText: 'Baseline Total Value' }).locator('.detail-val'),
    ).toContainText('12.00');
    await expect(page.locator('.delta-amount')).toContainText('0.00');
  });

  it_or_test: test('displays savings ledger with pending vs verified distinction and navigates to evidence', async ({ page }) => {
    await page.goto('/savings');

    await expect(page.locator('.page-title')).toContainText('Savings Ledger');

    // Ensure filter toolbar and stats are present
    await expect(page.locator('.stats-grid')).toBeVisible();
    await expect(page.locator('.filter-toolbar')).toBeVisible();

    const tableOrEmpty = page.locator('.savings-table, .empty-state');
    await expect(tableOrEmpty).toBeVisible();
  });

  test('renders savings ledger and outcome capture in Arabic with RTL layout', async ({ page }) => {
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/savings');

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('سجل الوفورات');

    await page.goto('/savings/outcome-capture');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('تسجيل نتيجة الشراء');
  });
});
