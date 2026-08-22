import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * End-to-End test suite for Self-Onboarding & Plan Gating (T057, US3).
 *
 * Requirements:
 * - FR-010: Starter plan display post-signup.
 * - FR-011: Limits messaging and visibility.
 * - FR-012: Stub billing provider transparency note.
 * - FR-016: Dual language (English and Arabic RTL).
 */
test.describe('Self-Onboarding & Plan Display (T057, US3)', () => {
  let owner: CreatedMember;

  test.beforeEach(async ({ page }) => {
    owner = await createMember('owner');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', owner.email);
    await page.fill('input[formControlName="password"]', owner.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('displays assigned Starter plan details and feature checklist', async ({ page }) => {
    await page.goto('/plan');

    await expect(page.locator('.page-title')).toContainText('Your Workspace Plan');
    await expect(page.locator('.plan-name')).toContainText('Starter');

    // Verify feature checklist
    const featureItems = page.locator('.feature-item');
    await expect(featureItems).toHaveCount(5);

    // Verify limit details
    await expect(page.locator('.limits-section')).toBeVisible();

    // Verify provider notice
    await expect(page.locator('.provider-note')).toBeVisible();

    // Verify continue button navigates to home
    await page.click('.continue-btn');
    await page.waitForURL('**/home');
  });

  test('renders plan display screen in Arabic with RTL layout', async ({ page }) => {
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/plan');

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('خطة مساحة العمل الخاصة بك');
  });
});
