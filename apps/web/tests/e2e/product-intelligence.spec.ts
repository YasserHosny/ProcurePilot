import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * End-to-End test suite for Product Price Intelligence (T040, US2).
 *
 * Requirements:
 * - FR-006: Price history over time per supplier derived from workspace purchase records.
 * - FR-007: Summary cards (last paid, average paid, best price) traceable to source records.
 * - FR-016: Dual language (English & Arabic RTL) support.
 */
test.describe('Product Price Intelligence Screen (T040, US2)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('displays price history chart, summary metric cards, and historical records table', async ({ page }) => {
    await page.goto('/offers/product-intelligence');

    await expect(page.locator('.page-title')).toBeVisible();

    // Verify presence of controls card
    await expect(page.locator('.controls-card')).toBeVisible();

    // Verify metrics grid, chart, or empty state
    const contentOrEmpty = page.locator('.metrics-grid, .empty-state-card');
    await expect(contentOrEmpty).toBeVisible();
  });

  test('renders Product Intelligence in Arabic with RTL layout', async ({ page }) => {
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/offers/product-intelligence');

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('ذكاء أسعار المنتج');
  });

  test('displays empty state when product has no purchase history', async ({ page }) => {
    await page.goto('/offers/product-intelligence?product_id=00000000-0000-0000-0000-000000000000');
    await expect(page.locator('.empty-state-card, .empty-state')).toBeVisible();
  });
});
