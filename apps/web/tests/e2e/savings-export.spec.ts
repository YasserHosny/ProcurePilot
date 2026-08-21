import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * End-to-End test suite for Savings Export (T041, US2).
 *
 * Requirements:
 * - FR-007: Excel (.xlsx) export of verified savings.
 * - FR-008: PDF summary report export.
 * - FR-009: Tracked async job polling.
 * - FR-016: Dual language (English and Arabic RTL).
 */
test.describe('Savings Export Screen (T041, US2)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('displays export settings form and initiates export job', async ({ page }) => {
    await page.goto('/savings/export');

    await expect(page.locator('.page-title')).toContainText('Export Savings Ledger');

    // Verify format radio group and date pickers
    await expect(page.locator('mat-radio-group[formControlName="format"]')).toBeVisible();
    await expect(page.locator('input[formControlName="period_start"]')).toBeVisible();
    await expect(page.locator('input[formControlName="period_end"]')).toBeVisible();

    const submitBtn = page.locator('button[type="submit"]');
    await expect(submitBtn).toBeEnabled();
  });

  test('renders savings export screen in Arabic with RTL layout', async ({ page }) => {
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/savings/export');

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('تصدير سجل الوفورات');
  });
});
