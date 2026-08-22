import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';
import {
  correctIssueDate,
  correctStatedTotal,
  saveCorrections,
  selectReviewSupplier,
  createE2ESupplier,
  uploadQuotationAndOpenReview,
} from './support/canonical-flow';

/**
 * End-to-End test suite for Arithmetic Mismatch Presentation & Confirmation Guardrail (T055, US3).
 *
 * Requirements:
 * - FR-010: System MUST validate line totals against stated total and force review when they differ.
 * - SC-003: 100% of mismatched-total quotations are held in mandatory review and cannot skip human review.
 *
 * The stub extraction provider always states £88.00 or £77.00 against a computed line total of
 * exactly £75.00, so every upload lands in mandatory review — no branching needed.
 */
test.describe('Quotation Arithmetic Mismatch (T055, US3)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('surfaces arithmetic mismatch banner with stated vs computed total breakdown and blocks confirmation', async ({ page }) => {
    const supplier = await createE2ESupplier();
    await uploadQuotationAndOpenReview(page, 'arithmetic_mismatch.pdf');

    // The mismatch banner is present on every stub upload — stated total is never 75.00.
    const banner = page.locator('.arithmetic-mismatch-banner');
    await expect(banner).toBeVisible();
    await expect(page.locator('.mismatch-title')).toContainText('Arithmetic Discrepancy Detected');

    // Breakdown: stated (88.00 or 77.00, hash-chosen) vs computed (always 75.00).
    const statedValue = page.locator('.breakdown-item').first().locator('.breakdown-val');
    await expect(statedValue).toHaveText(/^\s*£(88|77)\.00\s*$/);
    const computedValue = page.locator('.breakdown-item').nth(1).locator('.breakdown-val');
    await expect(computedValue).toHaveText(/^\s*£75\.00\s*$/);
    await expect(page.locator('.breakdown-item.diff-item')).toBeVisible();

    // SC-003: confirmation is genuinely blocked while the mismatch persists.
    await expect(page.locator('button.confirm-btn')).toBeDisabled();

    // A human reconciles the discrepancy (stated → computed) and resolves the low-confidence
    // issue date; only then is the guardrail released.
    await selectReviewSupplier(page, supplier.name);
    await correctStatedTotal(page);
    await correctIssueDate(page);
    await saveCorrections(page);

    // The banner (and its breakdown) only renders while the mismatch persists.
    await expect(banner).toBeHidden();
    await expect(page.locator('button.confirm-btn')).toBeEnabled();
  });
});
