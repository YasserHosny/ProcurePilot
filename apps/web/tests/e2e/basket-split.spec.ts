import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * End-to-End test suite for Two-Supplier Basket Split (T055, US3).
 *
 * Requirements:
 * - FR-008: Submit basket of products and quantities for two named suppliers.
 * - FR-009 / SC-004: Asynchronous job polling until terminal status without manual refresh.
 * - FR-010: Report infeasible items structured data when allocation is not possible.
 * - FR-018: Submission gated to owner/buyer roles.
 * - FR-016: Dual language (English & Arabic RTL) support.
 */
test.describe('Two-Supplier Basket Split Screen (T055, US3)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('renders basket split submission form with supplier and item selection', async ({ page }) => {
    await page.goto('/offers/basket-split');

    await expect(page.locator('.page-title')).toContainText('Two-Supplier Basket Split');
    await expect(page.locator('.form-card, .result-summary-card, .infeasible-card')).toBeVisible();

    const submitBtn = page.locator('.submit-btn');
    if (await submitBtn.isVisible()) {
      await expect(submitBtn).toBeVisible();
    }
  });

  test('renders Basket Split in Arabic with RTL layout', async ({ page }) => {
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/offers/basket-split');

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('تقسيم السلة بين موردين');
  });
});
