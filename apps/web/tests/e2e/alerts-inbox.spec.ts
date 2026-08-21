import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * End-to-End test suite for Alerts Inbox (T068, US4).
 *
 * Requirements:
 * - FR-012: Live alerts for expiring price, disappeared preferred offer, and price swings.
 * - FR-013: Dismiss individual alert.
 * - FR-016: Dual language (English & Arabic RTL) support.
 */
test.describe('Alerts Inbox Screen (T068, US4)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('displays actionable alerts list or all-clear empty state', async ({ page }) => {
    await page.goto('/alerts');

    await expect(page.locator('.page-title')).toContainText('Actionable Alerts Inbox');

    // Verify filter card or alert cards or empty state
    const content = page.locator('.alerts-list, .empty-state-card');
    await expect(content).toBeVisible();

    const dismissBtn = page.locator('.dismiss-btn').first();
    if (await dismissBtn.isVisible()) {
      await dismissBtn.click();
      // Verify toast or list update
      await expect(page.locator('.mat-mdc-snack-bar-container')).toBeVisible({ timeout: 5000 });
    }
  });

  test('renders Alerts Inbox in Arabic with RTL layout', async ({ page }) => {
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/alerts');

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('صندوق التنبيهات');
  });
});
