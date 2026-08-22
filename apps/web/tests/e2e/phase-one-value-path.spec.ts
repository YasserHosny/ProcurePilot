import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';
import {
  confirmQuotation,
  correctIssueDate,
  correctStatedTotal,
  resolveLineAsNewProduct,
  saveCorrections,
  selectReviewSupplier,
  uploadQuotationAndOpenReview,
} from './support/canonical-flow';

/**
 * Phase 1 Canonical Value Path E2E (T075).
 *
 * Drives the single ordered journey a customer takes through every Phase 1 capability, against
 * the real stack with no mocking:
 *   catalogue product → supplier → quotation upload → extraction review & correction →
 *   confirmation → matching → match resolution (new catalogue product) → Smart Compare
 *   recommendation with landed cost → purchase outcome capture → saving verification.
 *
 * Determinism notes: the stub extraction provider always extracts two lines totalling exactly
 * £75.00 against a stated total of £88.00 or £77.00, with a sub-threshold issue date — so the
 * correction recipe below is required on every run. Resolving the tomato line as a new 1×10 kg
 * product pins the created product's pack_base_quantity at 10 kg, which makes every Smart
 * Compare number deterministic too: a required quantity of 10 kg is exactly one pack, so the
 * projected landed cost equals the line's own £12.00 pack price (£1.20 per kg).
 */
test.describe('Phase 1 Complete Canonical Value Path (T075)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('walks the canonical procurement path from catalogue creation to a verified saving', async ({ page }) => {
    // The full journey — two creation forms, upload, review, confirmation, resolution,
    // comparison, capture, evidence, verification — needs more than the default minute.
    test.setTimeout(180_000);
    const stamp = Date.now();

    // 1. Create a catalogue product through the UI.
    const existingProductName = `E2E Path Anchor Product ${stamp}`;
    await page.goto('/products/new');
    await expect(page.locator('.page-title')).toContainText('Create Product');
    await page.fill('input[formControlName="tenant_name"]', existingProductName);
    // The select trigger collapses under the floating label on this form, so click the whole
    // form field — Material opens the option panel for a click anywhere in the field.
    await page
      .locator('mat-form-field', { hasText: 'Base Measurement Unit' })
      .click();
    await page.locator('mat-option', { hasText: '(each)' }).click();
    await page.fill('input[formControlName="pack_count"]', '1');
    await page.fill('input[formControlName="unit_size"]', '1');
    await page.locator('button[type="submit"]').click();
    await page.waitForURL('**/products');
    await expect(page.locator('.page-title')).toContainText('Product Master');

    // 2. Create a supplier through the UI.
    const supplierName = `E2E Path Supplier ${stamp}`;
    await page.goto('/suppliers/new');
    await expect(page.locator('.page-title')).toContainText('Create Supplier');
    await page.fill('input[formControlName="name"]', supplierName);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL('**/suppliers');

    // 3. Upload a real quotation PDF and open the review screen.
    const quotationId = await uploadQuotationAndOpenReview(page, `canonical_path_${stamp}.pdf`);

    // 4. Review: correct the stated total (reconciles arithmetic), correct the low-confidence
    //    issue date, confirm the supplier, save, then authorize the quotation.
    await selectReviewSupplier(page, supplierName);
    await correctStatedTotal(page);
    await correctIssueDate(page);
    await saveCorrections(page);
    await confirmQuotation(page);

    // 5. Resolve the tomato line's match task by creating a new catalogue product (1 × 10 kg,
    //    pre-filled from the line's own pack data). No earlier spec in the run resolves a
    //    tomato line, so no alias can auto-match it first — this must always go through the
    //    resolution UI.
    const matchedProductName = `E2E Path Tomatoes 10kg ${stamp}`;
    const match = await resolveLineAsNewProduct(
      page,
      quotationId,
      'Tomatoes case 10 kg',
      matchedProductName,
    );
    expect(
      match.via,
      'the canonical path must exercise the match resolution UI, not an alias auto-accept',
    ).toBe('ui_resolution');
    const matchedProduct = { id: match.productId };

    // 6. Smart Compare for the newly created product: the resolved line is its only offer.
    await page.goto(`/offers/compare?product_id=${matchedProduct.id}`);

    await expect(page.locator('.page-title')).toContainText('Smart Compare');
    await expect(page.locator('.recommendation-card')).toBeVisible({ timeout: 15000 });
    // Bug #4 guard: Required Quantity is in the product's normalised base unit.
    await expect(page.locator('.quantity-field mat-hint')).toHaveText('Unit: kg');

    const quantityValue = parseFloat(
      await page.inputValue('.quantity-input'),
    );
    const recommendedUnitPrice = parseMoney(
      await page.locator('.unit-price-sub strong').innerText(),
    );
    const recommendedLandedCost = parseMoney(
      await page.locator('.cost-amount').innerText(),
    );
    // Landed cost must equal the normalised unit price times the required quantity — a pack
    // count misinterpretation would inflate this by the 10 kg pack size.
    expect(Math.abs(recommendedUnitPrice * quantityValue - recommendedLandedCost)).toBeLessThan(
      0.01,
    );
    expect(recommendedLandedCost).toBeCloseTo(12.0, 2);
    await expect(page.locator('.offers-table tr.mat-mdc-row')).toHaveCount(1);

    // 7. Record the purchase against the recommended offer.
    await page.locator('.record-purchase-btn').click();
    await page.waitForURL('**/savings/outcome-capture**');

    const capturedQuantity = parseFloat(
      await page.inputValue('input[formControlName="quantity"]'),
    );
    const capturedUnitPrice = parseFloat(
      await page.inputValue('input[formControlName="unit_price_amount"]'),
    );
    const capturedTotalPaid = parseFloat(
      await page.inputValue('input[formControlName="total_paid_amount"]'),
    );
    expect(capturedQuantity).toBe(quantityValue);
    expect(capturedUnitPrice).toBeCloseTo(recommendedUnitPrice, 4);
    expect(capturedTotalPaid).toBeCloseTo(recommendedLandedCost, 4);
    expect(Math.abs(capturedQuantity * capturedUnitPrice - capturedTotalPaid)).toBeLessThan(0.01);

    await page.fill('input[formControlName="ordered_at"]', '2026-08-21');
    await page.locator('button[type="submit"].submit-btn').click();
    await page.waitForURL('**/savings/**/evidence');

    // 8. Evidence view: the whole chain joins without error, and the calculation is shown.
    await expect(page.locator('.error-banner')).toHaveCount(0);
    await expect(page.locator('.pending-banner')).toBeVisible();
    await expect(
      page.locator('.detail-row', { hasText: 'Actual Total Value' }).locator('.detail-val'),
    ).toContainText('12.00');
    await expect(
      page.locator('.detail-row', { hasText: 'Baseline Total Value' }).locator('.detail-val'),
    ).toContainText('12.00');
    await expect(page.locator('.delta-amount')).toContainText('0.00');
    await expect(page.locator('.competing-offer-row').first()).toBeVisible();

    // 9. Verify the saving — it becomes immutable.
    await page.locator('.verify-action-btn').click();
    await expect(page.locator('.immutable-banner')).toBeVisible();
    await expect(page.locator('.immutable-banner .banner-title')).toHaveText(
      'Verified (Immutable)',
    );
  });
});

/** Parses a rendered money string like "£12.00" into a number. */
function parseMoney(rendered: string): number {
  const value = parseFloat(rendered.replace(/[^0-9.-]/g, ''));
  if (isNaN(value)) {
    throw new Error(`Could not parse money value from "${rendered}"`);
  }
  return value;
}
