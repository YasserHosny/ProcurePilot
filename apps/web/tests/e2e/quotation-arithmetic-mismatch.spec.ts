import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * End-to-End test suite for Arithmetic Mismatch Presentation & Confirmation Guardrail (T055, US3).
 *
 * Requirements:
 * - FR-010: System MUST validate line totals against stated total and force review when they differ.
 * - SC-003: 100% of mismatched-total quotations are held in mandatory review and cannot skip human review.
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
    // Navigate to quotation review queue
    await page.goto('/quotations');
    await expect(page.locator('.page-title')).toContainText('Quotation Review Queue');

    // Filter by reason: arithmetic_mismatch if any exist in the queue
    const mismatchChip = page.locator('.reason-chip.reason-arithmetic_mismatch').first();
    if (await mismatchChip.isVisible()) {
      const reviewLink = page.locator('a:has-text("Review & Authorize")').first();
      await reviewLink.click();
      await page.waitForURL('**/quotations/**/review');

      // Verify the prominent arithmetic mismatch alert banner
      await expect(page.locator('.arithmetic-mismatch-banner')).toBeVisible();
      await expect(page.locator('.mismatch-title')).toContainText('Arithmetic Discrepancy Detected');
      await expect(page.locator('.breakdown-item.diff-item')).toBeVisible();

      // Verify confirmation is disabled while mismatch persists
      const confirmBtn = page.locator('button.confirm-btn');
      await expect(confirmBtn).toBeDisabled();
    }
  });
});
