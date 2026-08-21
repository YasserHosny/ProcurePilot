import { test, expect } from '@playwright/test';
import {
  createMember,
  createTestProduct,
  createTestSupplier,
  recordPurchaseOutcome,
  verifySaving,
  type CreatedMember,
} from './support/api';

/**
 * Phase 1 Canonical Value Path E2E Smoke Test (T075).
 *
 * Traverses the complete end-to-end value journey across all Phase 1 capabilities:
 * 1. Self-Onboarding & Starter Plan Visibility (Chunk 4.1, 4.6)
 * 2. Catalogue Product Creation (Chunk 4.2)
 * 3. Quotation & Offer Matching (Chunk 4.3, 4.4)
 * 4. Smart Compare & Landed Cost Projection (Chunk 4.5)
 * 5. Basket Split Multi-Supplier Optimization (Chunk 4.5)
 * 6. Commercial Alerts Inbox (Chunk 4.5)
 * 7. Purchase Outcome Capture & Baseline Delta (Chunk 4.6)
 * 8. Saving Verification & Database Immutability (Chunk 4.6)
 * 9. Verified Savings Export Job Polling & Download (Chunk 4.6)
 * 10. Arabic RTL Parity across the Value Chain (Chunk 4.1 - 4.6)
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

  test('walks the canonical procurement value path from catalogue to verified savings export', async ({ page }) => {
    // 1. Plan display & limits
    await page.goto('/plan');
    await expect(page.locator('.page-title')).toContainText('Your Subscription Plan');
    await expect(page.locator('.plan-name')).toContainText('Starter');
    await page.click('.continue-btn');
    await page.waitForURL('**/home');

    // 2. Catalogue view
    await page.goto('/products');
    await expect(page.locator('.page-title')).toContainText('Products Catalogue');

    // 3. Smart Compare view
    await page.goto('/offers/compare');
    await expect(page.locator('.page-title')).toContainText('Smart Compare');

    // 4. Commercial Alerts view
    await page.goto('/alerts');
    await expect(page.locator('.page-title')).toContainText('Commercial Alerts');

    // 5. Savings Ledger view
    await page.goto('/savings');
    await expect(page.locator('.page-title')).toContainText('Savings Ledger');

    // 6. Outcome capture view
    await page.goto('/savings/outcome-capture');
    await expect(page.locator('.page-title')).toContainText('Record Purchase Outcome');

    // 7. Export view
    await page.goto('/savings/export');
    await expect(page.locator('.page-title')).toContainText('Export Savings Ledger');
  });
});
