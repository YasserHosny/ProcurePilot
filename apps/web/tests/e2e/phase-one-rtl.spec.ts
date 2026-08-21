import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * Phase 1 Whole-Product RTL Verification (T069, US4).
 *
 * Verifies that switching to Arabic correctly updates html dir/lang attributes
 * and maintains structural layout integrity across all Phase 1 views.
 */
test.describe('Phase 1 Whole-Product RTL Layout (T069)', () => {
  let member: CreatedMember;

  test.beforeEach(async ({ page }) => {
    member = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', member.email);
    await page.fill('input[formControlName="password"]', member.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');

    // Switch to Arabic
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ar');
  });

  test('Savings Ledger renders correctly in RTL', async ({ page }) => {
    await page.goto('/savings');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('سجل الوفورات');
  });

  test('Outcome Capture renders correctly in RTL', async ({ page }) => {
    await page.goto('/savings/outcome-capture');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('تسجيل نتيجة الشراء');
  });

  test('Savings Export renders correctly in RTL', async ({ page }) => {
    await page.goto('/savings/export');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('تصدير سجل الوفورات');
  });

  test('Subscription Plan renders correctly in RTL', async ({ page }) => {
    await page.goto('/plan');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('خطة مساحة العمل الخاصة بك');
  });

  test('Smart Compare and Offers render correctly in RTL', async ({ page }) => {
    await page.goto('/offers/compare');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('مقارنة العروض الذكية');
  });

  test('Commercial Alerts Inbox renders correctly in RTL', async ({ page }) => {
    await page.goto('/alerts');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('صندوق التنبيهات الإجرائية');
  });
});
